"""
Exception hierarchy for the Bitbucket SDK.

All exceptions inherit from BitbucketError so callers can catch broadly or narrowly:

    try:
        pr = client.pull_requests.get(workspace, repo, pr_id)
    except NotFoundError:
        print("PR does not exist")
    except AuthenticationError:
        print("Check your credentials")
    except BitbucketError as e:
        print(f"Unexpected error: {e}")
"""


class BitbucketError(Exception):
    """Base class for all Bitbucket SDK errors."""


class AuthenticationError(BitbucketError):
    """Raised on HTTP 401. Credentials are missing or invalid."""


class PermissionError(BitbucketError):
    """Raised on HTTP 403. Authenticated user lacks access to the resource."""


class NotFoundError(BitbucketError):
    """Raised on HTTP 404. The workspace, repo, or resource does not exist."""


class ValidationError(BitbucketError):
    """Raised on HTTP 400. The request body or parameters were invalid."""


class RateLimitError(BitbucketError):
    """
    Raised on HTTP 429. Too many requests — tenacity will retry this automatically.

    The ``retry_after`` attribute reflects the ``Retry-After`` response header when
    present, so the retry wait strategy can honour the server's requested delay.
    """

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(message)


class APIError(BitbucketError):
    """Raised for any other 4xx or 5xx response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")
