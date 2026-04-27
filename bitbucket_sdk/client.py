"""
BitbucketClient — the single entry point for SDK users.

Usage:

    from bitbucket_sdk import BitbucketClient

    # Credentials from environment variables (BITBUCKET_EMAIL, BITBUCKET_API_TOKEN)
    client = BitbucketClient()

    # Explicit credentials
    client = BitbucketClient(email="me@example.com", api_token="ATATxxxxxxx")

    # Custom timeout (seconds)
    client = BitbucketClient(timeout=60)

    # Use as a context manager to ensure the connection pool is closed cleanly
    with BitbucketClient() as client:
        repos = client.repositories.list("myworkspace")
"""

from __future__ import annotations

from typing import Optional

from .auth import APITokenAuth
from ._http import HTTPClient, _DEFAULT_TIMEOUT
from .resources.repositories import RepositoriesResource
from .resources.pull_requests import PullRequestsResource


class BitbucketClient:
    """
    Top-level client for the Bitbucket Cloud REST API v2.0.

    Attributes:
        repositories:  Access repository operations.
        pull_requests: Access pull request operations.
    """

    def __init__(
        self,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        """
        Create a new BitbucketClient.

        Args:
            email:     Atlassian account email. Falls back to BITBUCKET_EMAIL env var.
            api_token: Atlassian API token.  Falls back to BITBUCKET_API_TOKEN env var.
                       Generate one at: https://id.atlassian.com/manage-profile/security/api-tokens
            timeout:   HTTP request timeout in seconds. Defaults to 30.
        """
        auth = APITokenAuth(email=email, api_token=api_token)
        self._http = HTTPClient(auth, timeout=timeout)

        self.repositories: RepositoriesResource = RepositoriesResource(self._http)
        self.pull_requests: PullRequestsResource = PullRequestsResource(self._http)

    # ------------------------------------------------------------------
    # Context manager — ensures the connection pool is released on exit
    # ------------------------------------------------------------------

    def __enter__(self) -> "BitbucketClient":
        return self

    def __exit__(self, *args) -> None:
        self._http.close()
