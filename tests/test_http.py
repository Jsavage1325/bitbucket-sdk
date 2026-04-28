"""
Unit tests for the internal HTTPClient (_http.py).

Covers:
  - HTTP status code → exception mapping (_raise_for_status)
  - User-Agent header is set on the session
  - Successful responses are decoded correctly
  - Empty responses return None
  - get_raw returns text
  - Retry-After value is stored on RateLimitError
  - Retry behaviour: succeeds after transient failures; exhausts retries on persistent 5xx
  - close() delegates to the session
  - Input validation in resource methods
"""

import unittest
from unittest.mock import MagicMock, patch, call

import requests

from bitbucket_sdk._http import HTTPClient, _raise_for_status, _DEFAULT_TIMEOUT
from bitbucket_sdk._version import __version__
from bitbucket_sdk.exceptions import (
    APIError,
    AuthenticationError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int, json_body=None, text: str = "", headers: dict = None):
    """Build a MagicMock that looks like a requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = text
    resp.content = text.encode() if text else b""

    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = ValueError("no JSON")

    return resp


def _make_client():
    """HTTPClient with a mocked session — no real network calls."""
    auth = MagicMock()
    client = HTTPClient(auth)
    client._session = MagicMock()
    return client


# ---------------------------------------------------------------------------
# _raise_for_status — error mapping
# ---------------------------------------------------------------------------


class TestRaiseForStatus(unittest.TestCase):

    def test_2xx_does_not_raise(self):
        for code in (200, 201, 204):
            _raise_for_status(_mock_response(code))  # no exception

    def test_400_raises_validation_error(self):
        resp = _mock_response(400, json_body={"error": {"message": "Bad field"}})
        with self.assertRaises(ValidationError):
            _raise_for_status(resp)

    def test_401_raises_authentication_error(self):
        resp = _mock_response(401, json_body={"error": {"message": "Unauthorized"}})
        with self.assertRaises(AuthenticationError):
            _raise_for_status(resp)

    def test_403_raises_permission_error(self):
        resp = _mock_response(403, json_body={"error": {"message": "Forbidden"}})
        with self.assertRaises(PermissionError):
            _raise_for_status(resp)

    def test_404_raises_not_found_error(self):
        resp = _mock_response(404, json_body={"error": {"message": "Not found"}})
        with self.assertRaises(NotFoundError):
            _raise_for_status(resp)

    def test_429_raises_rate_limit_error(self):
        resp = _mock_response(429, text="rate limited")
        with self.assertRaises(RateLimitError):
            _raise_for_status(resp)

    def test_429_stores_retry_after_header(self):
        resp = _mock_response(429, text="rate limited", headers={"Retry-After": "42"})
        with self.assertRaises(RateLimitError) as ctx:
            _raise_for_status(resp)
        self.assertEqual(ctx.exception.retry_after, 42.0)

    def test_429_retry_after_is_none_when_header_absent(self):
        resp = _mock_response(429, text="rate limited")
        with self.assertRaises(RateLimitError) as ctx:
            _raise_for_status(resp)
        self.assertIsNone(ctx.exception.retry_after)

    def test_500_raises_api_error(self):
        resp = _mock_response(500, json_body={"error": {"message": "Server error"}})
        with self.assertRaises(APIError) as ctx:
            _raise_for_status(resp)
        self.assertEqual(ctx.exception.status_code, 500)

    def test_503_raises_api_error_with_status_code(self):
        resp = _mock_response(503, text="Service unavailable")
        with self.assertRaises(APIError) as ctx:
            _raise_for_status(resp)
        self.assertEqual(ctx.exception.status_code, 503)

    def test_non_json_error_body_uses_text(self):
        resp = _mock_response(404, text="plain text error")
        with self.assertRaises(NotFoundError) as ctx:
            _raise_for_status(resp)
        self.assertIn("plain text error", str(ctx.exception))


# ---------------------------------------------------------------------------
# HTTPClient — headers and setup
# ---------------------------------------------------------------------------


class TestHTTPClientSetup(unittest.TestCase):

    def test_user_agent_header_is_set(self):
        auth = MagicMock()
        client = HTTPClient(auth)
        self.assertEqual(
            client._session.headers["User-Agent"],
            f"bitbucket-sdk-python/{__version__}",
        )

    def test_accept_json_header_is_set(self):
        auth = MagicMock()
        client = HTTPClient(auth)
        self.assertEqual(client._session.headers["Accept"], "application/json")

    def test_default_timeout(self):
        auth = MagicMock()
        client = HTTPClient(auth)
        self.assertEqual(client._timeout, _DEFAULT_TIMEOUT)

    def test_custom_timeout(self):
        auth = MagicMock()
        client = HTTPClient(auth, timeout=60)
        self.assertEqual(client._timeout, 60)


# ---------------------------------------------------------------------------
# HTTPClient — successful responses
# ---------------------------------------------------------------------------


class TestHTTPClientRequests(unittest.TestCase):

    def test_get_decodes_json(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(
            200, json_body={"values": [{"name": "repo"}]}, text='{"values":[{"name":"repo"}]}'
        )

        result = client.get("/repositories/ws")

        self.assertEqual(result["values"][0]["name"], "repo")

    def test_get_passes_params(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(200, json_body={}, text="{}")

        client.get("/some/path", params={"state": "OPEN"})

        _, kwargs = client._session.request.call_args
        self.assertEqual(kwargs["params"], {"state": "OPEN"})

    def test_get_raw_returns_text(self):
        client = _make_client()
        diff_text = "--- a/f.py\n+++ b/f.py\n"
        client._session.request.return_value = _mock_response(200, text=diff_text)

        result = client.get_raw("/some/diff")

        self.assertEqual(result, diff_text)

    def test_post_sends_json_body(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(
            201, json_body={"id": 1}, text='{"id":1}'
        )

        client.post("/some/path", json={"title": "My PR"})

        _, kwargs = client._session.request.call_args
        self.assertEqual(kwargs["json"], {"title": "My PR"})

    def test_empty_response_returns_none(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(204, text="")

        result = client.post("/some/path")

        self.assertIsNone(result)

    def test_delete_calls_correct_method(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(204, text="")

        client.delete("/some/path")

        args, _ = client._session.request.call_args
        self.assertEqual(args[0], "DELETE")

    def test_get_next_page_uses_full_url(self):
        """get_next_page must NOT prepend the base URL — the next URL is already complete."""
        client = _make_client()
        full_url = "https://api.bitbucket.org/2.0/repositories/ws?page=2"
        client._session.request.return_value = _mock_response(200, json_body={"values": []}, text="{}")

        client.get_next_page(full_url)

        args, _ = client._session.request.call_args
        self.assertEqual(args[1], full_url)

    def test_close_closes_session(self):
        client = _make_client()
        client.close()
        client._session.close.assert_called_once()


# ---------------------------------------------------------------------------
# HTTPClient — retry behaviour
# ---------------------------------------------------------------------------


class TestHTTPClientRetry(unittest.TestCase):

    def test_succeeds_after_one_transient_500(self):
        """Should succeed on the second attempt when the first returns a 500."""
        client = _make_client()
        client._session.request.side_effect = [
            _mock_response(500, json_body={"error": {"message": "oops"}}, text="oops"),
            _mock_response(200, json_body={"values": []}, text='{"values":[]}'),
        ]

        result = client.get("/some/path")

        self.assertEqual(client._session.request.call_count, 2)
        self.assertEqual(result, {"values": []})

    def test_raises_after_exhausting_retries_on_persistent_500(self):
        """Should raise APIError after 3 failed attempts."""
        client = _make_client()
        client._session.request.return_value = _mock_response(
            500, json_body={"error": {"message": "down"}}, text="down"
        )

        with self.assertRaises(APIError) as ctx:
            client.get("/some/path")

        self.assertEqual(client._session.request.call_count, 3)
        self.assertEqual(ctx.exception.status_code, 500)

    def test_does_not_retry_on_404(self):
        """404 is a caller error — should raise immediately without retrying."""
        client = _make_client()
        client._session.request.return_value = _mock_response(
            404, json_body={"error": {"message": "not found"}}, text="not found"
        )

        with self.assertRaises(NotFoundError):
            client.get("/some/path")

        self.assertEqual(client._session.request.call_count, 1)

    def test_does_not_retry_on_401(self):
        """401 must not be retried — credentials won't improve on their own."""
        client = _make_client()
        client._session.request.return_value = _mock_response(
            401, json_body={"error": {"message": "unauthorized"}}, text="unauthorized"
        )

        with self.assertRaises(AuthenticationError):
            client.get("/some/path")

        self.assertEqual(client._session.request.call_count, 1)


# ---------------------------------------------------------------------------
# Input validation in resource methods
# ---------------------------------------------------------------------------


class TestInputValidation(unittest.TestCase):

    def _pr_resource(self):
        from bitbucket_sdk.resources.pull_requests import PullRequestsResource
        return PullRequestsResource(MagicMock())

    def _repo_resource(self):
        from bitbucket_sdk.resources.repositories import RepositoriesResource
        return RepositoriesResource(MagicMock())

    def test_empty_workspace_raises_value_error(self):
        resource = self._pr_resource()
        with self.assertRaises(ValueError):
            resource.list("", "myrepo")

    def test_whitespace_workspace_raises_value_error(self):
        resource = self._pr_resource()
        with self.assertRaises(ValueError):
            resource.list("   ", "myrepo")

    def test_empty_repo_raises_value_error(self):
        resource = self._pr_resource()
        with self.assertRaises(ValueError):
            resource.list("myworkspace", "")

    def test_empty_body_in_post_comment_raises_value_error(self):
        resource = self._pr_resource()
        with self.assertRaises(ValueError):
            resource.post_comment("ws", "repo", 42, "")

    def test_empty_workspace_in_repo_list_raises(self):
        resource = self._repo_resource()
        with self.assertRaises(ValueError):
            resource.list("")

    def test_empty_commits_in_get_commit_diff_raises(self):
        resource = self._repo_resource()
        with self.assertRaises(ValueError):
            resource.get_commit_diff("ws", "repo", "")


# ---------------------------------------------------------------------------
# Authentication providers
# ---------------------------------------------------------------------------


class TestAPITokenAuth(unittest.TestCase):

    def test_raises_if_email_missing(self):
        from bitbucket_sdk.auth import APITokenAuth
        with self.assertRaises(ValueError) as ctx:
            APITokenAuth(email=None, api_token="token")
        self.assertIn("email", str(ctx.exception).lower())

    def test_raises_if_token_missing(self):
        from bitbucket_sdk.auth import APITokenAuth
        with self.assertRaises(ValueError) as ctx:
            APITokenAuth(email="me@example.com", api_token=None)
        self.assertIn("api token", str(ctx.exception).lower())

    def test_reads_credentials_from_env(self):
        from bitbucket_sdk.auth import APITokenAuth
        import os
        env = {"BITBUCKET_EMAIL": "env@example.com", "BITBUCKET_API_TOKEN": "envtoken"}
        with patch.dict(os.environ, env):
            auth = APITokenAuth()
        self.assertIsNotNone(auth)

    def test_sets_basic_auth_header(self):
        from bitbucket_sdk.auth import APITokenAuth
        import base64, requests as req_lib
        auth = APITokenAuth(email="me@example.com", api_token="mytoken")
        prepared = req_lib.Request("GET", "https://example.com").prepare()
        auth(prepared)
        expected = "Basic " + base64.b64encode(b"me@example.com:mytoken").decode()
        self.assertEqual(prepared.headers.get("Authorization"), expected)


class TestAccessTokenAuth(unittest.TestCase):

    def test_raises_if_token_missing(self):
        from bitbucket_sdk.auth import AccessTokenAuth
        with self.assertRaises(ValueError) as ctx:
            AccessTokenAuth(access_token=None)
        self.assertIn("access token", str(ctx.exception).lower())

    def test_reads_token_from_env(self):
        from bitbucket_sdk.auth import AccessTokenAuth
        import os
        with patch.dict(os.environ, {"BITBUCKET_ACCESS_TOKEN": "myoauthtoken"}):
            auth = AccessTokenAuth()
        self.assertIsNotNone(auth)

    def test_sets_bearer_header(self):
        from bitbucket_sdk.auth import AccessTokenAuth
        import requests as req_lib
        auth = AccessTokenAuth(access_token="mytoken123")
        prepared = req_lib.Request("GET", "https://example.com").prepare()
        auth(prepared)
        self.assertEqual(prepared.headers["Authorization"], "Bearer mytoken123")

    def test_explicit_token_overrides_env(self):
        from bitbucket_sdk.auth import AccessTokenAuth
        import os, requests as req_lib
        with patch.dict(os.environ, {"BITBUCKET_ACCESS_TOKEN": "envtoken"}):
            auth = AccessTokenAuth(access_token="explicit")
        prepared = req_lib.Request("GET", "https://example.com").prepare()
        auth(prepared)
        self.assertEqual(prepared.headers["Authorization"], "Bearer explicit")


class TestBitbucketClientAuthSelection(unittest.TestCase):
    """BitbucketClient should choose the right auth provider based on arguments."""

    def test_uses_access_token_auth_when_access_token_provided(self):
        from bitbucket_sdk import BitbucketClient
        from bitbucket_sdk.auth import AccessTokenAuth
        client = BitbucketClient(access_token="mytoken")
        self.assertIsInstance(client._http._session.auth, AccessTokenAuth)

    def test_uses_access_token_auth_from_env(self):
        from bitbucket_sdk import BitbucketClient
        from bitbucket_sdk.auth import AccessTokenAuth
        import os
        with patch.dict(os.environ, {"BITBUCKET_ACCESS_TOKEN": "envtoken"}, clear=False):
            client = BitbucketClient()
        self.assertIsInstance(client._http._session.auth, AccessTokenAuth)

    def test_uses_api_token_auth_when_no_access_token(self):
        from bitbucket_sdk import BitbucketClient
        from bitbucket_sdk.auth import APITokenAuth
        import os
        env = {
            "BITBUCKET_EMAIL": "me@example.com",
            "BITBUCKET_API_TOKEN": "token",
        }
        # Ensure BITBUCKET_ACCESS_TOKEN is not set
        clean_env = {k: v for k, v in os.environ.items() if k != "BITBUCKET_ACCESS_TOKEN"}
        clean_env.update(env)
        with patch.dict(os.environ, clean_env, clear=True):
            client = BitbucketClient()
        self.assertIsInstance(client._http._session.auth, APITokenAuth)


if __name__ == "__main__":
    unittest.main()
