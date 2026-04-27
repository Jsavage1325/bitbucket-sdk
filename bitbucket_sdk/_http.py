"""
Internal HTTP client for the Bitbucket SDK.

This module is intentionally private (leading underscore). It is an implementation
detail — SDK users interact only with resource classes, never with HTTPClient directly.

Key responsibilities:
  - Manages a requests.Session with auth, User-Agent, and default headers
  - Exposes get / get_raw / get_next_page / post / put / delete
  - Maps HTTP status codes to typed SDK exceptions
  - Applies retry logic via tenacity for transient failures
  - Respects the Retry-After header when rate-limited

Retry policy (tenacity):
  - Up to 3 attempts total
  - Waits for the Retry-After header value on HTTP 429; falls back to exponential
    backoff (1s → 2s → 4s, capped at 10s) for all other retryable errors
  - Retries on: connection errors, timeouts, HTTP 429, HTTP 5xx
  - Does NOT retry on: 400, 401, 403, 404 (caller errors, not transient)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    before_sleep_log,
)

from ._version import __version__
from .auth import APITokenAuth
from .exceptions import (
    APIError,
    AuthenticationError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ValidationError,
)

_BASE_URL = "https://api.bitbucket.org/2.0"
_DEFAULT_TIMEOUT = 30  # seconds

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------


def _should_retry(exc: BaseException) -> bool:
    """Return True for transient errors that are safe to retry."""
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIError) and exc.status_code >= 500:
        return True
    return False


def _retry_wait(retry_state) -> float:
    """
    Honour Retry-After header on 429; use exponential backoff for everything else.
    Backoff sequence: 1s, 2s, 4s (capped at 10s).
    """
    exc = retry_state.outcome.exception()
    if isinstance(exc, RateLimitError) and exc.retry_after is not None:
        logger.debug("Rate limited — waiting %.1fs (Retry-After header)", exc.retry_after)
        return float(exc.retry_after)
    wait = min(2 ** (retry_state.attempt_number - 1), 10)
    return float(wait)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


class HTTPClient:
    """
    Thin wrapper around requests.Session.

    All resource classes receive an instance of this client. They never touch
    requests directly, which makes them easy to test by mocking this class.
    """

    def __init__(self, auth: APITokenAuth, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout
        self._session = requests.Session()
        self._session.auth = auth
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": f"bitbucket-sdk-python/{__version__}",
        })

    # ------------------------------------------------------------------
    # Public interface — used by resource classes
    # ------------------------------------------------------------------

    def get(self, path: str, params: Optional[dict] = None) -> Any:
        """GET a path relative to the API base URL; decode JSON response."""
        return self._do("GET", _BASE_URL + path, params=params)

    def get_raw(self, path: str) -> str:
        """GET a path and return raw response text (used for diffs)."""
        return self._do_raw("GET", _BASE_URL + path)

    def get_next_page(self, url: str) -> Any:
        """
        Fetch a full pagination URL returned in a PagedList.next field.
        Unlike get(), the URL is used as-is (the base URL is already embedded).
        """
        return self._do("GET", url)

    def post(self, path: str, json: Optional[Any] = None) -> Any:
        """POST to a path; decode JSON response (or return None for empty bodies)."""
        return self._do("POST", _BASE_URL + path, json=json)

    def put(self, path: str, json: Optional[Any] = None) -> Any:
        """PUT to a path; decode JSON response."""
        return self._do("PUT", _BASE_URL + path, json=json)

    def delete(self, path: str) -> None:
        """DELETE a path."""
        self._do("DELETE", _BASE_URL + path)

    def close(self) -> None:
        """Close the underlying connection pool. Called automatically by context manager."""
        self._session.close()

    # ------------------------------------------------------------------
    # Internal — retry-wrapped request execution
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=_retry_wait,
        retry=retry_if_exception(_should_retry),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _do(self, method: str, url: str, **kwargs) -> Any:
        logger.debug("--> %s %s", method, url)
        response = self._session.request(method, url, timeout=self._timeout, **kwargs)
        logger.debug("<-- %s %s", response.status_code, url)
        _raise_for_status(response)
        if not response.content:
            return None
        return response.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=_retry_wait,
        retry=retry_if_exception(_should_retry),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _do_raw(self, method: str, url: str, **kwargs) -> str:
        logger.debug("--> %s %s (raw)", method, url)
        response = self._session.request(method, url, timeout=self._timeout, **kwargs)
        logger.debug("<-- %s %s", response.status_code, url)
        _raise_for_status(response)
        return response.text


# ---------------------------------------------------------------------------
# Status code → exception mapping
# ---------------------------------------------------------------------------


def _raise_for_status(response: requests.Response) -> None:
    """Convert HTTP error responses into typed SDK exceptions."""
    code = response.status_code
    if code < 400:
        return

    try:
        detail = response.json().get("error", {}).get("message", response.text)
    except Exception:
        detail = response.text

    if code == 400:
        raise ValidationError(detail)
    if code == 401:
        raise AuthenticationError(
            f"{detail}. Check your credentials or regenerate your API token at "
            "https://id.atlassian.com/manage-profile/security/api-tokens"
        )
    if code == 403:
        raise PermissionError(detail)
    if code == 404:
        raise NotFoundError(detail)
    if code == 429:
        retry_after_header = response.headers.get("Retry-After")
        retry_after = float(retry_after_header) if retry_after_header else None
        raise RateLimitError(retry_after=retry_after)
    raise APIError(code, detail)
