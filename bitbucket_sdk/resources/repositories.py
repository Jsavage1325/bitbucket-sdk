"""
RepositoriesResource — accessed via client.repositories

Methods:
  list(workspace, updated_since=None)         →  PagedList[Repository]  (first page)
  list_all(workspace, updated_since=None)     →  Iterator[Repository]   (all pages)
  get_commit_diff(workspace, repo, commits)   →  str
"""

from __future__ import annotations

from typing import Iterator, Optional

from .._http import HTTPClient
from ..models import PagedList, Repository


class RepositoriesResource:
    """
    Provides access to the /repositories Bitbucket API namespace.

    Do not instantiate directly — use BitbucketClient.repositories instead.
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    # ------------------------------------------------------------------
    # list_repos — single page
    # ------------------------------------------------------------------

    def list(
        self,
        workspace: str,
        updated_since: Optional[str] = None,
    ) -> PagedList[Repository]:
        """
        List repositories in a workspace (first page only).

        For all pages use ``list_all()``.

        Args:
            workspace:     Bitbucket workspace slug (e.g. "myteam").
            updated_since: ISO-8601 date string — only return repos updated after
                           this date (e.g. "2024-01-01"). Maps to the ``after`` query param.

        Returns:
            PagedList[Repository] — iterable, supports len().
        """
        _require("workspace", workspace)
        params: dict = {}
        if updated_since:
            params["after"] = updated_since

        data = self._http.get(f"/repositories/{workspace}", params=params or None)
        return _parse_repo_page(data)

    # ------------------------------------------------------------------
    # list_all — auto-paginating generator
    # ------------------------------------------------------------------

    def list_all(
        self,
        workspace: str,
        updated_since: Optional[str] = None,
    ) -> Iterator[Repository]:
        """
        Yield every repository in a workspace, transparently fetching all pages.

        Usage::

            for repo in client.repositories.list_all("myworkspace"):
                print(repo.full_name)

        Args:
            workspace:     Bitbucket workspace slug.
            updated_since: ISO-8601 date string filter (see ``list()``).
        """
        page = self.list(workspace, updated_since=updated_since)
        yield from page.values
        while page.next:
            data = self._http.get_next_page(page.next)
            page = _parse_repo_page(data)
            yield from page.values

    # ------------------------------------------------------------------
    # get_commit_diff
    # ------------------------------------------------------------------

    def get_commit_diff(
        self,
        workspace: str,
        repo: str,
        commits: str,
    ) -> str:
        """
        Retrieve the raw unified diff for one or more commits.

        Args:
            workspace: Bitbucket workspace slug.
            repo:      Repository slug.
            commits:   A single commit hash (``"abc1234"``) or a range (``"abc..def"``).

        Returns:
            The raw diff as a string (unified diff format).
        """
        _require("workspace", workspace)
        _require("repo", repo)
        _require("commits", commits)
        return self._http.get_raw(f"/repositories/{workspace}/{repo}/diff/{commits}")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_repo_page(data: dict) -> PagedList[Repository]:
    repos = [Repository.from_dict(r) for r in data.get("values", [])]
    return PagedList(
        values=repos,
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
