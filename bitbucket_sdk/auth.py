"""
Authentication providers for the Bitbucket SDK.

Two providers are available:

APITokenAuth  — Atlassian API token (Basic Auth)
    Credentials: BITBUCKET_EMAIL + BITBUCKET_API_TOKEN env vars
    Header:      Authorization: Basic base64(email:token)
    Get a token: https://id.atlassian.com/manage-profile/security/api-tokens

AccessTokenAuth — OAuth 2.0 / workspace access token (Bearer Auth)
    Credential:  BITBUCKET_ACCESS_TOKEN env var
    Header:      Authorization: Bearer {token}
    Use when:    You already hold an OAuth access token or a Bitbucket
                 workspace/repository access token and want to use it directly
                 without the full OAuth flow.

Both extend requests.auth.AuthBase, which is the standard hook point that the
requests library calls before sending every HTTP request.
"""

import os

from requests.auth import AuthBase, HTTPBasicAuth


class APITokenAuth(AuthBase):
    """Authenticates using an Atlassian API token (HTTP Basic Auth)."""

    def __init__(self, email: str | None = None, api_token: str | None = None) -> None:
        resolved_email = email or os.environ.get("BITBUCKET_EMAIL")
        resolved_token = api_token or os.environ.get("BITBUCKET_API_TOKEN")

        if not resolved_email:
            raise ValueError(
                "Bitbucket email is required. "
                "Set the BITBUCKET_EMAIL environment variable or pass email= to BitbucketClient."
            )
        if not resolved_token:
            raise ValueError(
                "Bitbucket API token is required. "
                "Set the BITBUCKET_API_TOKEN environment variable or pass api_token= to BitbucketClient. "
                "Create a token at: https://id.atlassian.com/manage-profile/security/api-tokens"
            )

        self._basic = HTTPBasicAuth(resolved_email, resolved_token)

    def __call__(self, request):
        """Called by requests before sending — attaches the Authorization header."""
        return self._basic(request)


class AccessTokenAuth(AuthBase):
    """
    Authenticates using a Bitbucket OAuth 2.0 or workspace access token (Bearer Auth).

    Use this when you already hold an access token — for example from a CI/CD
    environment variable, a Bitbucket workspace access token, or a previously
    completed OAuth flow — and want to use it directly.

    The token is read from the BITBUCKET_ACCESS_TOKEN environment variable by
    default, or passed explicitly via the constructor.
    """

    def __init__(self, access_token: str | None = None) -> None:
        resolved = access_token or os.environ.get("BITBUCKET_ACCESS_TOKEN")

        if not resolved:
            raise ValueError(
                "Bitbucket access token is required. "
                "Set the BITBUCKET_ACCESS_TOKEN environment variable or pass "
                "access_token= to BitbucketClient."
            )

        self._token = resolved

    def __call__(self, request):
        """Called by requests before sending — attaches the Bearer Authorization header."""
        request.headers["Authorization"] = f"Bearer {self._token}"
        return request
