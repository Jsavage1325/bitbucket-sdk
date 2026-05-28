"""
PullRequestsResource — accessed via client.pull_requests

Methods:
  list(workspace, repo, state="OPEN")           →  PagedList[PullRequest]
  list_all(workspace, repo, state="OPEN")        →  Iterator[PullRequest]
  get_open(workspace, repo, branch=None)         →  PullRequest
  get(workspace, repo, pr_id)                    →  PullRequest
  get_diff(workspace, repo, pr_id)               →  str
  get_diffstat(workspace, repo, pr_id)           →  PagedList[DiffStat]
  list_comments(workspace, repo, pr_id)          →  PagedList[Comment]
  list_all_comments(workspace, repo, pr_id)      →  Iterator[Comment]
  list_unresolved_comments(...)                  →  list[Comment]
  post_comment(..., parent_id=None)              →  Comment   (pass parent_id for threaded replies)
  resolve_comment(...)                           →  None
  approve(workspace, repo, pr_id)               →  None
  unapprove(workspace, repo, pr_id)             →  None
  decline(workspace, repo, pr_id)               →  PullRequest
  merge(workspace, repo, pr_id, strategy=..., close_source_branch=None, message=None)  →  PullRequest
  create(..., reviewers=None, close_source_branch=False)                               →  PullRequest
  update(workspace, repo, pr_id, title=None, description=None, reviewers=None,
         destination_branch=None, close_source_branch=None)                            →  PullRequest
"""

from __future__ import annotations

from typing import Iterator, List, Optional

from .._http import HTTPClient
from ..exceptions import NotFoundError
from ..models import Comment, DiffStat, PagedList, PullRequest


class PullRequestsResource:
    """
    Provides access to the /repositories/{workspace}/{repo}/pullrequests API.

    Do not instantiate directly — use BitbucketClient.pull_requests instead.
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    # ------------------------------------------------------------------
    # list — single page
    # ------------------------------------------------------------------

    def list(
        self,
        workspace: str,
        repo: str,
        state: str = "OPEN",
    ) -> PagedList[PullRequest]:
        """
        List pull requests filtered by state (first page only).

        For all pages use ``list_all()``.

        Args:
            workspace: Bitbucket workspace slug.
            repo:      Repository slug.
            state:     ``"OPEN"`` (default), ``"MERGED"``, ``"DECLINED"``, ``"SUPERSEDED"``.

        Returns:
            PagedList[PullRequest]
        """
        _require("workspace", workspace)
        _require("repo", repo)
        data = self._http.get(_pr_base(workspace, repo), params={"state": state})
        return _parse_pr_page(data)

    # ------------------------------------------------------------------
    # list_all — auto-paginating generator
    # ------------------------------------------------------------------

    def list_all(
        self,
        workspace: str,
        repo: str,
        state: str = "OPEN",
    ) -> Iterator[PullRequest]:
        """
        Yield every pull request matching the given state, fetching all pages.

        Usage::

            for pr in client.pull_requests.list_all("myworkspace", "myrepo"):
                print(pr.id, pr.title)
        """
        page = self.list(workspace, repo, state=state)
        yield from page.values
        while page.next:
            data = self._http.get_next_page(page.next)
            page = _parse_pr_page(data)
            yield from page.values

    # ------------------------------------------------------------------
    # get_open
    # ------------------------------------------------------------------

    def get_open(
        self,
        workspace: str,
        repo: str,
        branch: Optional[str] = None,
    ) -> PullRequest:
        """
        Return a single open PR, optionally filtered by source branch name.

        If ``branch`` is ``None``, returns the first open PR found.
        Raises ``NotFoundError`` if no matching open PR exists.

        Args:
            workspace: Bitbucket workspace slug.
            repo:      Repository slug.
            branch:    Source branch name to match (optional).
        """
        page = self.list(workspace, repo, state="OPEN")
        for pr in page:
            if branch is None or pr.source.branch_name == branch:
                return pr
        msg = f"no open PR found for branch '{branch}'" if branch else "no open PRs found"
        raise NotFoundError(msg)

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------

    def get(self, workspace: str, repo: str, pr_id: int) -> PullRequest:
        """
        Fetch a single pull request by its numeric ID.

        Args:
            workspace: Bitbucket workspace slug.
            repo:      Repository slug.
            pr_id:     The PR number (e.g. 42).
        """
        _require("workspace", workspace)
        _require("repo", repo)
        data = self._http.get(_pr_path(workspace, repo, pr_id))
        return PullRequest.from_dict(data)

    # ------------------------------------------------------------------
    # get_diff
    # ------------------------------------------------------------------

    def get_diff(self, workspace: str, repo: str, pr_id: int) -> str:
        """
        Retrieve the raw unified diff for a pull request.

        Returns:
            Diff as a string in unified diff format.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        return self._http.get_raw(f"{_pr_path(workspace, repo, pr_id)}/diff")

    # ------------------------------------------------------------------
    # get_diffstat
    # ------------------------------------------------------------------

    def get_diffstat(
        self, workspace: str, repo: str, pr_id: int
    ) -> PagedList[DiffStat]:
        """
        Retrieve per-file change statistics for a pull request.

        Returns:
            PagedList[DiffStat] — each entry describes one changed file.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        data = self._http.get(f"{_pr_path(workspace, repo, pr_id)}/diffstat")
        stats = [DiffStat.from_dict(s) for s in data.get("values", [])]
        return PagedList(
            values=stats,
            size=data.get("size", 0),
            page=data.get("page", 1),
            pagelen=data.get("pagelen", 0),
            next=data.get("next"),
            previous=data.get("previous"),
        )

    # ------------------------------------------------------------------
    # list_comments — single page
    # ------------------------------------------------------------------

    def list_comments(
        self, workspace: str, repo: str, pr_id: int
    ) -> PagedList[Comment]:
        """
        List all comments on a pull request (inline and general), first page only.

        For all pages use ``list_all_comments()``.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        data = self._http.get(f"{_pr_path(workspace, repo, pr_id)}/comments")
        return _parse_comment_page(data)

    # ------------------------------------------------------------------
    # list_all_comments — auto-paginating generator
    # ------------------------------------------------------------------

    def list_all_comments(
        self, workspace: str, repo: str, pr_id: int
    ) -> Iterator[Comment]:
        """
        Yield every comment on a pull request, fetching all pages.

        Usage::

            for comment in client.pull_requests.list_all_comments("ws", "repo", 42):
                print(comment.user.display_name, comment.content.raw)
        """
        page = self.list_comments(workspace, repo, pr_id)
        yield from page.values
        while page.next:
            data = self._http.get_next_page(page.next)
            page = _parse_comment_page(data)
            yield from page.values

    # ------------------------------------------------------------------
    # list_unresolved_comments
    # ------------------------------------------------------------------

    def list_unresolved_comments(
        self,
        workspace: str,
        repo: str,
        pr_id: int,
        inline_only: bool = False,
    ) -> List[Comment]:
        """
        Return only unresolved comments on a pull request.

        Uses ``list_all_comments()`` internally so all pages are considered.

        Args:
            workspace:   Bitbucket workspace slug.
            repo:        Repository slug.
            pr_id:       The PR number.
            inline_only: If ``True``, only return unresolved *inline* comments.
        """
        results = [
            c for c in self.list_all_comments(workspace, repo, pr_id)
            if not c.resolved and not c.deleted
        ]
        if inline_only:
            results = [c for c in results if c.is_inline]
        return results

    # ------------------------------------------------------------------
    # post_comment
    # ------------------------------------------------------------------

    def post_comment(
        self,
        workspace: str,
        repo: str,
        pr_id: int,
        body: str,
        file_path: Optional[str] = None,
        line: Optional[int] = None,
        parent_id: Optional[int] = None,
    ) -> Comment:
        """
        Post a comment on a pull request.

        Three modes:
          - General comment:  pass only ``body``.
          - Inline comment:   pass ``body`` + ``file_path`` + ``line``.
          - Threaded reply:   pass ``body`` + ``parent_id``. Bitbucket inherits
                              the inline location from the parent automatically,
                              so ``file_path`` / ``line`` are not required for
                              replies to inline comments.

        Args:
            workspace: Bitbucket workspace slug.
            repo:      Repository slug.
            pr_id:     The PR number.
            body:      Comment text (Markdown supported).
            file_path: File path for an inline comment — must be paired with ``line``.
            line:      Line number (1-based) — must be paired with ``file_path``.
            parent_id: ID of an existing comment to reply to. When set, the new
                       comment is threaded under that parent.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        _require("body", body)

        payload: dict = {"content": {"raw": body}}

        if file_path is not None and line is not None:
            payload["inline"] = {"path": file_path, "to": line}
        elif file_path is not None or line is not None:
            raise ValueError(
                "Both 'file_path' and 'line' must be provided together for an inline comment."
            )

        if parent_id is not None:
            payload["parent"] = {"id": parent_id}

        data = self._http.post(f"{_pr_path(workspace, repo, pr_id)}/comments", json=payload)
        return Comment.from_dict(data)

    # ------------------------------------------------------------------
    # resolve_comment
    # ------------------------------------------------------------------

    def resolve_comment(
        self, workspace: str, repo: str, pr_id: int, comment_id: int
    ) -> None:
        """
        Mark an inline comment thread as resolved.

        Args:
            workspace:  Bitbucket workspace slug.
            repo:       Repository slug.
            pr_id:      The PR number.
            comment_id: The numeric ID of the comment to resolve.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        self._http.post(f"{_pr_path(workspace, repo, pr_id)}/comments/{comment_id}/resolve")

    # ------------------------------------------------------------------
    # approve / unapprove
    # ------------------------------------------------------------------

    def approve(self, workspace: str, repo: str, pr_id: int) -> None:
        """Approve a pull request as the authenticated user."""
        _require("workspace", workspace)
        _require("repo", repo)
        self._http.post(f"{_pr_path(workspace, repo, pr_id)}/approve")

    def unapprove(self, workspace: str, repo: str, pr_id: int) -> None:
        """Remove the authenticated user's approval from a pull request."""
        _require("workspace", workspace)
        _require("repo", repo)
        self._http.delete(f"{_pr_path(workspace, repo, pr_id)}/approve")

    # ------------------------------------------------------------------
    # decline
    # ------------------------------------------------------------------

    def decline(self, workspace: str, repo: str, pr_id: int) -> PullRequest:
        """
        Decline a pull request.

        Returns:
            PullRequest with state ``"DECLINED"``.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        data = self._http.post(f"{_pr_path(workspace, repo, pr_id)}/decline")
        return PullRequest.from_dict(data)

    # ------------------------------------------------------------------
    # merge
    # ------------------------------------------------------------------

    def merge(
        self,
        workspace: str,
        repo: str,
        pr_id: int,
        strategy: str = "merge_commit",
        close_source_branch: Optional[bool] = None,
        message: Optional[str] = None,
    ) -> PullRequest:
        """
        Merge a pull request.

        Args:
            workspace:           Bitbucket workspace slug.
            repo:                Repository slug.
            pr_id:               The PR number.
            strategy:            ``"merge_commit"`` (default), ``"squash"``,
                                 or ``"fast_forward"``.
            close_source_branch: If ``True``, delete the source branch after
                                 merging. If ``None`` (default), the PR's own
                                 setting is used.
            message:             Custom merge commit message. Only used when
                                 ``strategy="merge_commit"`` or ``"squash"``.

        Returns:
            PullRequest with state ``"MERGED"``.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        payload: dict = {"merge_strategy": strategy}
        if close_source_branch is not None:
            payload["close_source_branch"] = close_source_branch
        if message is not None:
            payload["message"] = message
        data = self._http.post(
            f"{_pr_path(workspace, repo, pr_id)}/merge",
            json=payload,
        )
        return PullRequest.from_dict(data)

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------

    def create(
        self,
        workspace: str,
        repo: str,
        title: str,
        source_branch: str,
        destination_branch: str,
        description: Optional[str] = None,
        reviewers: Optional[List[str]] = None,
        close_source_branch: bool = False,
    ) -> PullRequest:
        """
        Create a new pull request.

        Args:
            workspace:           Bitbucket workspace slug.
            repo:                Repository slug.
            title:               PR title.
            source_branch:       The branch containing the changes.
            destination_branch:  The branch to merge into.
            description:         Optional PR description (Markdown supported).
            reviewers:           Optional list of reviewer UUIDs
                                 (e.g. ``["{abc-123}", "{def-456}"]``).
                                 UUIDs can be found via the Bitbucket UI or API.
            close_source_branch: If ``True``, delete the source branch after
                                 merging. Defaults to ``False``.

        Returns:
            The newly created PullRequest.
        """
        _require("workspace", workspace)
        _require("repo", repo)
        _require("title", title)
        _require("source_branch", source_branch)
        _require("destination_branch", destination_branch)

        payload: dict = {
            "title": title,
            "source": {"branch": {"name": source_branch}},
            "destination": {"branch": {"name": destination_branch}},
            "close_source_branch": close_source_branch,
        }
        if description is not None:
            payload["description"] = description
        if reviewers:
            payload["reviewers"] = [{"uuid": uuid} for uuid in reviewers]

        data = self._http.post(_pr_base(workspace, repo), json=payload)
        return PullRequest.from_dict(data)

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------

    def update(
        self,
        workspace: str,
        repo: str,
        pr_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        reviewers: Optional[List[str]] = None,
        destination_branch: Optional[str] = None,
        close_source_branch: Optional[bool] = None,
    ) -> PullRequest:
        """
        Update an existing pull request.

        Only fields that are explicitly passed (non-None) are sent. Bitbucket
        *replaces* (does not merge) the reviewers list — pass the full desired
        list, or omit the parameter entirely to leave reviewers unchanged. Pass
        ``reviewers=[]`` to clear all reviewers.

        Args:
            workspace:           Bitbucket workspace slug.
            repo:                Repository slug.
            pr_id:               The PR number to update.
            title:               New PR title.
            description:         New PR description (Markdown supported).
            reviewers:           Full replacement list of reviewer UUIDs.
                                 Pass ``[]`` to clear, omit to leave unchanged.
            destination_branch:  Re-target the PR to a different destination.
            close_source_branch: Whether to delete the source branch on merge.

        Returns:
            The updated PullRequest.

        Raises:
            ValueError: if no updatable field is provided.
        """
        _require("workspace", workspace)
        _require("repo", repo)

        payload: dict = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if reviewers is not None:
            payload["reviewers"] = [{"uuid": uuid} for uuid in reviewers]
        if destination_branch is not None:
            payload["destination"] = {"branch": {"name": destination_branch}}
        if close_source_branch is not None:
            payload["close_source_branch"] = close_source_branch

        if not payload:
            raise ValueError(
                "update() requires at least one field to change "
                "(title, description, reviewers, destination_branch, close_source_branch)"
            )

        data = self._http.put(_pr_path(workspace, repo, pr_id), json=payload)
        return PullRequest.from_dict(data)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _pr_base(workspace: str, repo: str) -> str:
    return f"/repositories/{workspace}/{repo}/pullrequests"


def _pr_path(workspace: str, repo: str, pr_id: int) -> str:
    return f"{_pr_base(workspace, repo)}/{pr_id}"


def _parse_pr_page(data: dict) -> PagedList[PullRequest]:
    prs = [PullRequest.from_dict(p) for p in data.get("values", [])]
    return PagedList(
        values=prs,
        size=data.get("size", 0),
        page=data.get("page", 1),
        pagelen=data.get("pagelen", 0),
        next=data.get("next"),
        previous=data.get("previous"),
    )


def _parse_comment_page(data: dict) -> PagedList[Comment]:
    comments = [Comment.from_dict(c) for c in data.get("values", [])]
    return PagedList(
        values=comments,
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
