"""
PipelinesResource — accessed via client.pipelines

Methods (reads):
  list(workspace, repo, ref=None, status=None, page_size=10)  →  PagedList[Pipeline]
  list_all(workspace, repo, ref=None, status=None)            →  Iterator[Pipeline]
  get(workspace, repo, pipeline_uuid)                         →  Pipeline
  list_steps(workspace, repo, pipeline_uuid)                  →  PagedList[PipelineStep]
  get_step_log(workspace, repo, pipeline_uuid, step_uuid,
               tail_lines=None)                                →  str
  list_test_cases(workspace, repo, pipeline_uuid, step_uuid)  →  PagedList[TestCase]

Methods (pipeline variables — repo-level env vars):
  list_variables(workspace, repo)                             →  list[PipelineVariable]
  set_variable(workspace, repo, key, value, secured=False)    →  PipelineVariable  (upsert)
  delete_variable(workspace, repo, key)                       →  None
"""

from __future__ import annotations

from typing import Iterator, List, Optional

from .._http import HTTPClient
from ..exceptions import NotFoundError
from ..models import PagedList, Pipeline, PipelineStep, PipelineVariable, TestCase


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


    # ------------------------------------------------------------------
    # list_variables — repo-level pipeline env vars, auto-paginated
    # ------------------------------------------------------------------

    def list_variables(self, workspace: str, repo: str) -> List[PipelineVariable]:
        """
        Return all repository-level pipeline variables.

        Auto-paginates across all pages (typical repos have <50 variables so
        this is rarely more than a single API call). Secured variables have
        value=None — Bitbucket never returns secured values via the API.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        results: List[PipelineVariable] = []
        path: Optional[str] = (
            f"/repositories/{workspace}/{repo}/pipelines_config/variables/"
        )
        params: Optional[dict] = {"pagelen": 100}
        while path:
            if params is None:
                # Subsequent pages: path is a full URL from the previous response's next
                data = self._http.get_next_page(path)
            else:
                data = self._http.get(path, params=params)
                params = None  # only the first page carries query params
            results.extend(
                PipelineVariable.from_dict(v) for v in data.get("values", [])
            )
            path = data.get("next")
        return results

    # ------------------------------------------------------------------
    # set_variable — upsert by key (POST if new, PUT if exists)
    # ------------------------------------------------------------------

    def set_variable(
        self,
        workspace: str,
        repo: str,
        key: str,
        value: str,
        secured: bool = False,
    ) -> PipelineVariable:
        """
        Create or update a repo-level pipeline variable.

        Looks up the variable by key first; POSTs a new variable when none
        exists, PUTs to the existing UUID otherwise. The value of a secured
        variable cannot be read back after it is set — only its key and
        ``secured=True`` will be returned by subsequent list_variables calls.

        Args:
            workspace: Bitbucket workspace slug.
            repo:      Repository slug.
            key:       Variable name (e.g. "AWS_ACCESS_KEY_ID_QA").
            value:     The value to store.
            secured:   If True, Bitbucket marks the variable as a secret and
                       its value is no longer readable via the API.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        _require("key", key)
        existing = next(
            (v for v in self.list_variables(workspace, repo) if v.key == key),
            None,
        )
        payload = {"key": key, "value": value, "secured": secured}
        base = f"/repositories/{workspace}/{repo}/pipelines_config/variables/"
        if existing is not None:
            data = self._http.put(f"{base}{existing.uuid}", json=payload)
        else:
            data = self._http.post(base, json=payload)
        return PipelineVariable.from_dict(data)

    # ------------------------------------------------------------------
    # delete_variable — by key (looks up UUID, then DELETE)
    # ------------------------------------------------------------------

    def delete_variable(self, workspace: str, repo: str, key: str) -> None:
        """
        Delete a repo-level pipeline variable by key.

        Raises NotFoundError if no variable with that key exists.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        _require("key", key)
        existing = next(
            (v for v in self.list_variables(workspace, repo) if v.key == key),
            None,
        )
        if existing is None:
            raise NotFoundError(
                f"Pipeline variable {key!r} not found in {workspace}/{repo}"
            )
        self._http.delete(
            f"/repositories/{workspace}/{repo}/pipelines_config/variables/{existing.uuid}"
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
