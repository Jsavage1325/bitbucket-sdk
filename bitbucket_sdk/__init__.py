"""
bitbucket_sdk — Python SDK for the Bitbucket Cloud REST API v2.0

Quick start:

    from bitbucket_sdk import BitbucketClient

    client = BitbucketClient()  # reads BITBUCKET_EMAIL and BITBUCKET_API_TOKEN from env

    repos = client.repositories.list("myworkspace")
    pr    = client.pull_requests.get("myworkspace", "myrepo", pr_id=42)

    # Context manager — closes the connection pool cleanly on exit
    with BitbucketClient() as client:
        diff = client.pull_requests.get_diff("myworkspace", "myrepo", 42)

Public surface:
  - BitbucketClient       main client (see client.py)
  - exceptions.*          typed exception classes
  - models.*              response dataclasses (PullRequest, Comment, Repository, …)
"""

from ._version import __version__
from .auth import AccessTokenAuth, APITokenAuth
from .client import BitbucketClient
from .exceptions import (
    APIError,
    AuthenticationError,
    BitbucketError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ValidationError,
)
from .models import (
    Comment,
    Content,
    DiffStat,
    Inline,
    PagedList,
    Participant,
    Pipeline,
    PipelineStep,
    PullRequest,
    Ref,
    Repository,
    SrcEntry,
    TestCase,
    User,
)

__all__ = [
    # Version
    "__version__",
    # Auth providers (for advanced use — most users only need BitbucketClient)
    "APITokenAuth",
    "AccessTokenAuth",
    # Client
    "BitbucketClient",
    # Exceptions
    "BitbucketError",
    "AuthenticationError",
    "PermissionError",
    "NotFoundError",
    "ValidationError",
    "RateLimitError",
    "APIError",
    # Models
    "PagedList",
    "Repository",
    "PullRequest",
    "Comment",
    "Content",
    "DiffStat",
    "Inline",
    "Participant",
    "Pipeline",
    "PipelineStep",
    "Ref",
    "SrcEntry",
    "TestCase",
    "User",
]
