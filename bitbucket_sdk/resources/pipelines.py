"""
PipelinesResource — accessed via client.pipelines

Methods:
  list(workspace, repo, ref=None, status=None, page_size=10)  →  PagedList[Pipeline]
  list_all(workspace, repo, ref=None, status=None)            →  Iterator[Pipeline]
  get(workspace, repo, pipeline_uuid)                         →  Pipeline
  list_steps(workspace, repo, pipeline_uuid)                  →  list[PipelineStep]
  get_step_log(workspace, repo, pipeline_uuid, step_uuid,
               tail_lines=None)                                →  str
  list_test_cases(workspace, repo, pipeline_uuid, step_uuid)  →  PagedList[TestCase]
"""

from __future__ import annotations

from typing import Iterator, Optional

from .._http import HTTPClient
from ..models import PagedList, Pipeline, PipelineStep, TestCase


class PipelinesResource:
    """
    Provides access to the /pipelines and /pipelines_config namespaces.

    Do not instantiate directly — use BitbucketClient.pipelines instead.
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    # ------------------------------------------------------------------
    # list — single page, sorted newest-first
    # ------------------------------------------------------------------

    def list(
        self,
        workspace: str,
        repo: str,
        ref: Optional[str] = None,
        status: Optional[str] = None,
        page_size: int = 10,
    ) -> PagedList[Pipeline]:
        """
        List pipeline runs (newest first), filtered optionally by branch ref or status.

        Args:
            workspace: Bitbucket workspace slug.
            repo:      Repository slug.
            ref:       Branch ref (target.ref_name) — e.g. "main", "develop", "feature/x".
            status:    Filter by state, e.g. "SUCCESSFUL", "FAILED", "IN_PROGRESS".
                       Passed through to Bitbucket; invalid values yield empty results.
            page_size: pagelen value (default 10, max 100 per Bitbucket).

        Returns:
            PagedList[Pipeline]
        """
        _require("workspace", workspace)
        _require("repo", repo)
        params: dict = {"sort": "-created_on", "pagelen": page_size}
        if ref:
            params["target.ref_name"] = ref
        if status:
            params["status"] = status
        data = self._http.get(f"/repositories/{workspace}/{repo}/pipelines/", params=params)
        return _parse_pipeline_page(data)

    # ------------------------------------------------------------------
    # list_all — auto-paginating generator
    # ------------------------------------------------------------------

    def list_all(
        self,
        workspace: str,
        repo: str,
        ref: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Iterator[Pipeline]:
        """Yield every pipeline matching the filter, across all pages."""
        page = self.list(workspace, repo, ref=ref, status=status, page_size=100)
        yield from page.values
        while page.next:
            data = self._http.get_next_page(page.next)
            page = _parse_pipeline_page(data)
            yield from page.values

    # ------------------------------------------------------------------
    # get — single pipeline run
    # ------------------------------------------------------------------

    def get(self, workspace: str, repo: str, pipeline_uuid: str) -> Pipeline:
        """Fetch a single pipeline by UUID (braces and dashes both accepted)."""
        _require("workspace", workspace)
        _require("repo", repo)
        _require("pipeline_uuid", pipeline_uuid)
        data = self._http.get(f"/repositories/{workspace}/{repo}/pipelines/{pipeline_uuid}")
        return Pipeline.from_dict(data)

    # ------------------------------------------------------------------
    # list_steps — steps within a pipeline run
    # ------------------------------------------------------------------

    def list_steps(
        self,
        workspace: str,
        repo: str,
        pipeline_uuid: str,
    ) -> PagedList[PipelineStep]:
        """List steps for a given pipeline run.

        Bitbucket returns these as a paginated envelope; the SDK preserves
        the envelope rather than flattening to a list, matching the convention
        used by ``pull_requests.get_diffstat`` etc.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        _require("pipeline_uuid", pipeline_uuid)
        data = self._http.get(
            f"/repositories/{workspace}/{repo}/pipelines/{pipeline_uuid}/steps/"
        )
        steps = [PipelineStep.from_dict(s) for s in data.get("values", [])]
        return PagedList(
            values=steps,
            size=data.get("size", 0),
            page=data.get("page", 1),
            pagelen=data.get("pagelen", 0),
            next=data.get("next"),
            previous=data.get("previous"),
        )

    # ------------------------------------------------------------------
    # get_step_log — raw log output, optionally tail-sliced
    # ------------------------------------------------------------------

    def get_step_log(
        self,
        workspace: str,
        repo: str,
        pipeline_uuid: str,
        step_uuid: str,
        tail_lines: Optional[int] = None,
    ) -> str:
        """
        Return the raw text log for a pipeline step.

        Args:
            tail_lines: When set, return only the last N lines. Implementation
                        fetches the full log then slices client-side — Bitbucket
                        doesn't support range-by-line on this endpoint and a
                        single API call is the same cost as a byte-range request.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        _require("pipeline_uuid", pipeline_uuid)
        _require("step_uuid", step_uuid)
        log = self._http.get_raw(
            f"/repositories/{workspace}/{repo}/pipelines/{pipeline_uuid}"
            f"/steps/{step_uuid}/log"
        )
        if tail_lines is None or tail_lines <= 0:
            return log
        lines = log.splitlines()
        return "\n".join(lines[-tail_lines:])

    # ------------------------------------------------------------------
    # list_test_cases — JUnit-style test results for a step
    # ------------------------------------------------------------------

    def list_test_cases(
        self,
        workspace: str,
        repo: str,
        pipeline_uuid: str,
        step_uuid: str,
    ) -> PagedList[TestCase]:
        """List test case results published by a pipeline step.

        Bitbucket Pipelines surfaces JUnit XML uploaded by steps via this
        endpoint. Returns an empty PagedList if the step didn't publish any.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        _require("pipeline_uuid", pipeline_uuid)
        _require("step_uuid", step_uuid)
        data = self._http.get(
            f"/repositories/{workspace}/{repo}/pipelines/{pipeline_uuid}"
            f"/steps/{step_uuid}/test_reports/test_cases/"
        )
        cases = [TestCase.from_dict(c) for c in data.get("values", [])]
        return PagedList(
            values=cases,
            size=data.get("size", 0),
            page=data.get("page", 1),
            pagelen=data.get("pagelen", 0),
            next=data.get("next"),
            previous=data.get("previous"),
        )


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_pipeline_page(data: dict) -> PagedList[Pipeline]:
    pipelines = [Pipeline.from_dict(p) for p in data.get("values", [])]
    return PagedList(
        values=pipelines,
        size=data.get("size", 0),
        page=data.get("page", 1),
        pagelen=data.get("pagelen", 0),
        next=data.get("next"),
        previous=data.get("previous"),
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _require(name: str, value: str) -> None:
    if not value or not str(value).strip():
        raise ValueError(f"'{name}' must not be empty")
