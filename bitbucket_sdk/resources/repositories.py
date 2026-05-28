"""
RepositoriesResource — accessed via client.repositories

Methods:
  list(workspace, updated_since=None)            →  PagedList[Repository]  (first page)
  list_all(workspace, updated_since=None)        →  Iterator[Repository]   (all pages)
  get_commit_diff(workspace, repo, commits)      →  str
  get_file(workspace, repo, path, ref=None)      →  str  (file contents at ref)
  list_directory(workspace, repo, path, ref)     →  PagedList[SrcEntry]    (directory listing)
"""

from __future__ import annotations

from typing import Iterator, Optional

from .._http import HTTPClient
from ..models import PagedList, Repository, SrcEntry
from ._utils import _require


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

    # ------------------------------------------------------------------
    # get_file — raw file contents at a branch / tag / commit
    # ------------------------------------------------------------------

    def get_file(
        self,
        workspace: str,
        repo: str,
        path: str,
        ref: Optional[str] = None,
    ) -> str:
        """
        Return the raw text contents of a file at a given ref.

        Args:
            workspace: Bitbucket workspace slug.
            repo:      Repository slug.
            path:      File path within the repo (no leading slash needed; one is stripped).
            ref:       Branch name, tag, or commit hash. When None, the repository's
                       default branch is looked up and used.

        Returns:
            The file content as a string. Binary files come back as best-effort-decoded
            strings via requests' charset detection — agents needing exact bytes should
            clone instead.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        _require("path", path)
        resolved_ref = self._resolve_ref(workspace, repo, ref)
        clean_path = path.lstrip("/")
        return self._http.get_raw(
            f"/repositories/{workspace}/{repo}/src/{resolved_ref}/{clean_path}"
        )

    # ------------------------------------------------------------------
    # list_directory — meta listing at a path
    # ------------------------------------------------------------------

    def list_directory(
        self,
        workspace: str,
        repo: str,
        path: str = "",
        ref: Optional[str] = None,
    ) -> PagedList[SrcEntry]:
        """
        List files and subdirectories at the given path.

        Args:
            workspace: Bitbucket workspace slug.
            repo:      Repository slug.
            path:      Directory path within the repo. Defaults to "" (repo root).
                       Leading slashes are stripped; trailing slash optional.
            ref:       Branch name, tag, or commit hash. When None, the repository's
                       default branch is looked up and used.

        Returns:
            PagedList[SrcEntry] — entries are files (type="commit_file") and
            subdirectories (type="commit_directory").
        """
        _require("workspace", workspace)
        _require("repo", repo)
        resolved_ref = self._resolve_ref(workspace, repo, ref)
        clean_path = path.lstrip("/")
        data = self._http.get(
            f"/repositories/{workspace}/{repo}/src/{resolved_ref}/{clean_path}",
            params={"format": "meta"},
        )
        return _parse_src_page(data)

    # ------------------------------------------------------------------
    # Internal — resolve a possibly-None ref to a concrete branch name
    # ------------------------------------------------------------------

    def _resolve_ref(
        self,
        workspace: str,
        repo: str,
        ref: Optional[str],
    ) -> str:
        """When ref is None, fetch the repo and use its default branch."""
        if ref:
            return ref
        data = self._http.get(f"/repositories/{workspace}/{repo}")
        main = (data.get("mainbranch") or {}).get("name")
        if not main:
            raise ValueError(
                f"Could not determine default branch for {workspace}/{repo}"
            )
        return main


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


def _parse_src_page(data: dict) -> PagedList[SrcEntry]:
    entries = [SrcEntry.from_dict(e) for e in data.get("values", [])]
    return PagedList(
        values=entries,
        size=data.get("size", 0),
        page=data.get("page", 1),
        pagelen=data.get("pagelen", 0),
        next=data.get("next"),
        previous=data.get("previous"),
    )


