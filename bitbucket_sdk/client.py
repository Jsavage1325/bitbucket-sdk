"""
BitbucketClient — the single entry point for SDK users.

Three authentication methods are supported:

    # 1. Atlassian API token (Basic Auth) — most common
    #    Reads BITBUCKET_EMAIL + BITBUCKET_API_TOKEN from environment
    client = BitbucketClient()

    # 2. Atlassian API token — explicit credentials
    client = BitbucketClient(email="me@example.com", api_token="ATATxxxxxxx")

    # 3. OAuth 2.0 / workspace access token (Bearer Auth)
    #    Reads BITBUCKET_ACCESS_TOKEN from environment
    client = BitbucketClient(access_token="eyJ...")

    # Custom timeout (seconds)
    client = BitbucketClient(timeout=60)

    # Use as a context manager to close the connection pool cleanly on exit
    with BitbucketClient() as client:
        repos = client.repositories.list("myworkspace")

Auth resolution order:
    If ``access_token`` (or BITBUCKET_ACCESS_TOKEN) is provided → Bearer auth.
    Otherwise → API token Basic auth (requires email + api_token).
"""

from __future__ import annotations

from typing import Optional

from .auth import AccessTokenAuth, APITokenAuth
from ._http import HTTPClient, _DEFAULT_TIMEOUT
from .resources.repositories import RepositoriesResource
from .resources.pull_requests import PullRequestsResource
from .resources.pipelines import PipelinesResource


class BitbucketClient:
    """
    Top-level client for the Bitbucket Cloud REST API v2.0.

    Attributes:
        repositories:  Access repository operations.
        pull_requests: Access pull request operations.
        pipelines:     Access pipeline runs, steps, logs, and test reports.
    """

    def __init__(
        self,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        """
        Create a new BitbucketClient.

        Args:
            email:        Atlassian account email for API token auth.
                          Falls back to BITBUCKET_EMAIL env var.
            api_token:    Atlassian API token for API token auth.
                          Falls back to BITBUCKET_API_TOKEN env var.
                          Generate at: https://id.atlassian.com/manage-profile/security/api-tokens
            access_token: OAuth 2.0 or workspace access token (Bearer auth).
                          Falls back to BITBUCKET_ACCESS_TOKEN env var.
                          When provided (or set in env), this takes precedence
                          over email/api_token.
            timeout:      HTTP request timeout in seconds. Defaults to 30.
        """
        import os

        # Access token takes precedence — check both explicit arg and env var
        _use_bearer = access_token or os.environ.get("BITBUCKET_ACCESS_TOKEN")

        if _use_bearer:
            auth = AccessTokenAuth(access_token=access_token)
        else:
            auth = APITokenAuth(email=email, api_token=api_token)

        self._http = HTTPClient(auth, timeout=timeout)
        self.repositories: RepositoriesResource = RepositoriesResource(self._http)
        self.pull_requests: PullRequestsResource = PullRequestsResource(self._http)
        self.pipelines: PipelinesResource = PipelinesResource(self._http)

    # ------------------------------------------------------------------
    # Context manager — ensures the connection pool is released on exit
    # ------------------------------------------------------------------

    def __enter__(self) -> "BitbucketClient":
        return self

    def __exit__(self, *args) -> None:
        self._http.close()
