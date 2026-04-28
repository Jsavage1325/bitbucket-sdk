"""
Dataclass models for Bitbucket Cloud REST API v2.0 responses.

All models are plain Python dataclasses — no external dependencies.
Datetime strings from the API are parsed to datetime objects in __post_init__.

Generic PagedList[T] mirrors the Go Paginated[T] and is iterable, so:

    for repo in client.repositories.list("myworkspace"):
        print(repo.full_name)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Generic, Iterator, List, Optional, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Pagination wrapper
# ---------------------------------------------------------------------------


@dataclass
class PagedList(Generic[T]):
    """Wrapper around Bitbucket's paginated response envelope."""

    values: List[T]
    size: int = 0
    page: int = 1
    pagelen: int = 0
    next: Optional[str] = None
    previous: Optional[str] = None

    def __iter__(self) -> Iterator[T]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)


# ---------------------------------------------------------------------------
# Primitive building blocks
# ---------------------------------------------------------------------------


@dataclass
class User:
    display_name: str = ""
    uuid: str = ""
    nickname: str = ""
    account_id: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        return cls(
            display_name=data.get("display_name", ""),
            uuid=data.get("uuid", ""),
            nickname=data.get("nickname", ""),
            account_id=data.get("account_id", ""),
        )


@dataclass
class Repository:
    full_name: str = ""
    name: str = ""
    uuid: str = ""
    scm: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Repository":
        return cls(
            full_name=data.get("full_name", ""),
            name=data.get("name", ""),
            uuid=data.get("uuid", ""),
            scm=data.get("scm", ""),
        )


@dataclass
class Ref:
    """A branch reference with its parent repository info."""

    branch_name: str = ""
    repo_full_name: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Ref":
        branch = data.get("branch", {})
        repo = data.get("repository", {})
        return cls(
            branch_name=branch.get("name", ""),
            repo_full_name=repo.get("full_name", ""),
        )


@dataclass
class Inline:
    """Inline comment location within a file."""

    path: str = ""
    from_line: Optional[int] = None
    to_line: Optional[int] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Inline":
        return cls(
            path=data.get("path", ""),
            from_line=data.get("from"),
            to_line=data.get("to"),
        )


@dataclass
class Content:
    raw: str = ""
    markup: str = ""
    html: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Content":
        return cls(
            raw=data.get("raw", ""),
            markup=data.get("markup", ""),
            html=data.get("html", ""),
        )


@dataclass
class Participant:
    user: User = field(default_factory=User)
    role: str = ""
    approved: bool = False
    state: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Participant":
        return cls(
            user=User.from_dict(data.get("user", {})),
            role=data.get("role", ""),
            approved=data.get("approved", False),
            state=data.get("state", ""),
        )


# ---------------------------------------------------------------------------
# Pull Request
# ---------------------------------------------------------------------------


@dataclass
class PullRequest:
    id: int = 0
    title: str = ""
    description: str = ""
    state: str = ""
    author: User = field(default_factory=User)
    source: Ref = field(default_factory=Ref)
    destination: Ref = field(default_factory=Ref)
    close_source_branch: bool = False
    created_on: Optional[datetime] = None
    updated_on: Optional[datetime] = None
    comment_count: int = 0
    task_count: int = 0
    reviewers: List[User] = field(default_factory=list)
    participants: List[Participant] = field(default_factory=list)
    merge_commit_hash: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "PullRequest":
        merge_commit = data.get("merge_commit") or {}
        return cls(
            id=data.get("id", 0),
            title=data.get("title", ""),
            description=data.get("description", ""),
            state=data.get("state", ""),
            author=User.from_dict(data.get("author", {})),
            source=Ref.from_dict(data.get("source", {})),
            destination=Ref.from_dict(data.get("destination", {})),
            close_source_branch=data.get("close_source_branch", False),
            created_on=_parse_dt(data.get("created_on")),
            updated_on=_parse_dt(data.get("updated_on")),
            comment_count=data.get("comment_count", 0),
            task_count=data.get("task_count", 0),
            reviewers=[User.from_dict(u) for u in data.get("reviewers", [])],
            participants=[Participant.from_dict(p) for p in data.get("participants", [])],
            merge_commit_hash=merge_commit.get("hash"),
        )


# ---------------------------------------------------------------------------
# Comment
# ---------------------------------------------------------------------------


@dataclass
class Comment:
    id: int = 0
    content: Content = field(default_factory=Content)
    user: User = field(default_factory=User)
    created_on: Optional[datetime] = None
    updated_on: Optional[datetime] = None
    inline: Optional[Inline] = None
    deleted: bool = False
    resolved: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "Comment":
        inline_data = data.get("inline")
        return cls(
            id=data.get("id", 0),
            content=Content.from_dict(data.get("content", {})),
            user=User.from_dict(data.get("user", {})),
            created_on=_parse_dt(data.get("created_on")),
            updated_on=_parse_dt(data.get("updated_on")),
            inline=Inline.from_dict(inline_data) if inline_data else None,
            deleted=data.get("deleted", False),
            resolved=data.get("resolution") is not None,
        )

    @property
    def is_inline(self) -> bool:
        return self.inline is not None


# ---------------------------------------------------------------------------
# DiffStat (new — not in Go CLI)
# ---------------------------------------------------------------------------


@dataclass
class DiffStat:
    """Statistics for a single file changed in a PR or commit."""

    status: str = ""          # "added", "removed", "modified", "renamed"
    lines_added: int = 0
    lines_removed: int = 0
    old_path: Optional[str] = None
    new_path: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "DiffStat":
        old_file = data.get("old") or {}
        new_file = data.get("new") or {}
        return cls(
            status=data.get("status", ""),
            lines_added=data.get("lines_added", 0),
            lines_removed=data.get("lines_removed", 0),
            old_path=old_file.get("path"),
            new_path=new_file.get("path"),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 datetime string from the API into a datetime object."""
    if not value:
        return None
    # Bitbucket returns strings like "2024-01-15T10:30:00.000000+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
