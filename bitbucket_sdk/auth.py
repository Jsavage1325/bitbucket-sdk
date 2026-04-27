"""
Authentication provider for the Bitbucket SDK.

Uses Atlassian API tokens with HTTP Basic Auth.

Credentials are read from environment variables by default:
    BITBUCKET_EMAIL      — your Atlassian account email address
    BITBUCKET_API_TOKEN  — token from id.atlassian.com/manage-profile/security/api-tokens

Constructor arguments override environment variables if provided.

    # From environment (recommended for scripts and CI)
    auth = APITokenAuth()

    # Explicit (useful in tests or when env vars aren't available)
    auth = APITokenAuth(email="me@example.com", api_token="ATATxxxxxxx")

This class extends requests.auth.AuthBase, which is the standard hook point that the
requests library calls before sending every HTTP request.
"""

import os

from requests.auth import AuthBase, HTTPBasicAuth


class APITokenAuth(AuthBase):
    """Authenticates requests using an Atlassian API token (Basic Auth)."""

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
