# Bitbucket Python SDK — Build Plan

## Overview

Port the existing Go-based `bb` CLI tool into a **Python SDK library** that Python programs can
import and use programmatically. The SDK exposes 15 functions covering repositories and pull
requests against the Bitbucket Cloud REST API v2.0.

Auth method: **Atlassian API Token** (Basic Auth)
Data models: **Python dataclasses**
Config: **Environment variables** (`BITBUCKET_EMAIL`, `BITBUCKET_API_TOKEN`)

---

## Package Layout

```
bitbucket_sdk/
├── __init__.py             # Public re-exports: BitbucketClient, exceptions, models
├── client.py               # BitbucketClient — the single entry point for SDK users
├── auth.py                 # APITokenAuth — wraps requests.AuthBase
├── exceptions.py           # Typed exception hierarchy
├── models.py               # @dataclass response types
├── _http.py                # Internal HTTP client (private, not part of public API)
└── resources/
    ├── __init__.py
    ├── repositories.py     # RepositoriesResource
    └── pull_requests.py    # PullRequestsResource

pyproject.toml              # Package metadata (dependencies: requests, tenacity)
tests/
├── test_repositories.py
└── test_pull_requests.py
```

---

## Authentication (`auth.py`)

`APITokenAuth(email?, api_token?)` implements `requests.auth.AuthBase`.

- Reads `BITBUCKET_EMAIL` and `BITBUCKET_API_TOKEN` from environment by default
- Falls back to constructor arguments if provided
- Produces: `Authorization: Basic base64(email:token)`

```python
client = BitbucketClient()                          # env vars
client = BitbucketClient(email="…", api_token="…") # explicit
```

API tokens are created at: https://id.atlassian.com/manage-profile/security/api-tokens

---

## HTTP Client (`_http.py`)

`HTTPClient` wraps `requests.Session`:
- Base URL: `https://api.bitbucket.org/2.0`
- 30-second timeout
- Methods: `get(path, params?)`, `post(path, json?)`, `put(path, json?)`, `delete(path)`
- Raises typed exceptions on HTTP errors (see below)
- Returns raw `str` for diff endpoints (not JSON)
- **Retry logic via `tenacity`**: all requests are wrapped with `@retry` using exponential
  backoff. Retries on network errors, HTTP 429 (rate limit), and HTTP 5xx (server errors).
  Non-retryable errors (401, 403, 404, 400) raise immediately without retry.

  ```python
  from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

  @retry(
      stop=stop_after_attempt(3),
      wait=wait_exponential(multiplier=1, min=1, max=10),
      retry=retry_if_exception_type((NetworkError, RateLimitError)),
  )
  def _request(self, ...): ...
  ```

---

## Exception Hierarchy (`exceptions.py`)

```
BitbucketError               ← base class
├── AuthenticationError      ← HTTP 401
├── PermissionError          ← HTTP 403
├── NotFoundError            ← HTTP 404
├── ValidationError          ← HTTP 400
└── APIError(status, msg)    ← all other 4xx / 5xx
```

---

## Data Models (`models.py`)

All response types are Python `@dataclass` classes. Dates are parsed to `datetime` objects.

| Dataclass       | Key fields |
|-----------------|------------|
| `PagedList[T]`  | `values: list[T]`, `size`, `page`, `next` (generic + iterable) |
| `Repository`    | `full_name`, `name`, `uuid` |
| `PullRequest`   | `id`, `title`, `state`, `source`, `destination`, `author` |
| `Comment`       | `id`, `content`, `user`, `inline?`, `created_on` |
| `DiffStat`      | `lines_added`, `lines_removed`, `status`, `old_path`, `new_path` |
| `User`          | `display_name`, `uuid`, `account_id` |
| `Ref`           | `branch_name`, `repo_full_name` |
| `Inline`        | `path`, `from_line?`, `to_line?` |

`PagedList[T]` supports `for item in paged_list` iteration.

---

## Main Client (`client.py`)

```python
class BitbucketClient:
    def __init__(self, email=None, api_token=None):
        auth = APITokenAuth(email=email, api_token=api_token)
        http = HTTPClient(auth)
        self.repositories  = RepositoriesResource(http)
        self.pull_requests = PullRequestsResource(http)
```

---

## Function → Method Mapping

### `client.repositories`

| Requested signature | SDK method | Endpoint |
|---------------------|------------|----------|
| `list_repos(workspace, updated_since?)` | `client.repositories.list(workspace, updated_since=None)` → `PagedList[Repository]` | `GET /repositories/{workspace}` |
| `get_commit_diff(workspace, repo, commits)` | `client.repositories.get_commit_diff(workspace, repo, commits)` → `str` | `GET /repositories/{workspace}/{repo}/diff/{commits}` |

### `client.pull_requests`

| Requested signature | SDK method | Endpoint |
|---------------------|------------|----------|
| `list_open_prs(workspace, repo)` | `client.pull_requests.list(workspace, repo, state='OPEN')` → `PagedList[PullRequest]` | `GET /repositories/{w}/{r}/pullrequests?state=OPEN` |
| `get_open_pr(workspace, repo, branch?)` | `client.pull_requests.get_open(workspace, repo, branch=None)` → `PullRequest` | Lists OPEN PRs, filters by source branch client-side |
| `get_pr(workspace, repo, pr_id)` | `client.pull_requests.get(workspace, repo, pr_id)` → `PullRequest` | `GET /repositories/{w}/{r}/pullrequests/{id}` |
| `get_pr_diff(workspace, repo, pr_id)` | `client.pull_requests.get_diff(workspace, repo, pr_id)` → `str` | `GET /repositories/{w}/{r}/pullrequests/{id}/diff` |
| `get_pr_diffstat(workspace, repo, pr_id)` | `client.pull_requests.get_diffstat(workspace, repo, pr_id)` → `PagedList[DiffStat]` | `GET /repositories/{w}/{r}/pullrequests/{id}/diffstat` |
| `get_pr_comments(workspace, repo, pr_id)` | `client.pull_requests.list_comments(workspace, repo, pr_id)` → `PagedList[Comment]` | `GET /repositories/{w}/{r}/pullrequests/{id}/comments` |
| `get_unresolved_pr_comments(workspace, repo, pr_id, inline_only?)` | `client.pull_requests.list_unresolved_comments(workspace, repo, pr_id, inline_only=False)` → `list[Comment]` | Fetches all comments, filters client-side |
| `post_pr_comment(workspace, repo, pr_id, body, file_path?, line?)` | `client.pull_requests.post_comment(workspace, repo, pr_id, body, file_path=None, line=None)` → `Comment` | `POST /repositories/{w}/{r}/pullrequests/{id}/comments` |
| `resolve_pr_comment(workspace, repo, pr_id, comment_id)` | `client.pull_requests.resolve_comment(workspace, repo, pr_id, comment_id)` | `POST /repositories/{w}/{r}/pullrequests/{id}/comments/{cid}/resolve` |
| `approve_pr(workspace, repo, pr_id)` | `client.pull_requests.approve(workspace, repo, pr_id)` | `POST /repositories/{w}/{r}/pullrequests/{id}/approve` |
| `decline_pr(workspace, repo, pr_id)` | `client.pull_requests.decline(workspace, repo, pr_id)` → `PullRequest` | `POST /repositories/{w}/{r}/pullrequests/{id}/decline` |
| `merge_pr(workspace, repo, pr_id, strategy?)` | `client.pull_requests.merge(workspace, repo, pr_id, strategy='merge_commit')` → `PullRequest` | `POST /repositories/{w}/{r}/pullrequests/{id}/merge` |
| `create_pr(workspace, repo, title, source_branch, destination_branch, description?)` | `client.pull_requests.create(workspace, repo, title, source_branch, destination_branch, description=None)` → `PullRequest` | `POST /repositories/{w}/{r}/pullrequests` |

---

## Inline Comment Design

When `file_path` and `line` are passed to `post_comment`, the JSON body includes:

```json
{
  "content": { "raw": "your comment text" },
  "inline":  { "path": "src/foo.py", "to": 42 }
}
```

---

## Key SDK Design Principles (for learning)

1. **Resources as sub-objects** (`client.pull_requests.get()` not `client.get_pr()`)
   — This is how AWS SDK (boto3), Stripe, GitHub, and Twilio all work.

2. **Private internals** (`_http.py` with leading underscore)
   — Communicates "not part of the public API" by Python convention.

3. **`__init__.py` re-exports** — Users write `from bitbucket_sdk import BitbucketClient`,
   not `from bitbucket_sdk.client import BitbucketClient`.

4. **Typed exceptions** — Callers can `except NotFoundError` instead of checking status codes.

5. **Generic `PagedList[T]`** — Demonstrates Python generics (`typing.Generic[T]`).

6. **Two external dependencies** — `requests` for HTTP and `tenacity` for retry logic.
   Tenacity decorates HTTP calls with exponential backoff, retrying on transient errors
   (network failures, HTTP 429 rate-limit, HTTP 5xx server errors) without any manual
   retry loops in business logic.

---

## Usage Example (after implementation)

```python
import os
from bitbucket_sdk import BitbucketClient

# Reads BITBUCKET_EMAIL and BITBUCKET_API_TOKEN from environment
client = BitbucketClient()

# List repos
repos = client.repositories.list("myworkspace")
for repo in repos:
    print(repo.full_name)

# List open PRs
prs = client.pull_requests.list("myworkspace", "myrepo")
pr  = client.pull_requests.get("myworkspace", "myrepo", pr_id=42)
print(pr.title, pr.state)

# Get diff
diff = client.pull_requests.get_diff("myworkspace", "myrepo", 42)
print(diff[:500])

# Post a comment
comment = client.pull_requests.post_comment(
    "myworkspace", "myrepo", 42,
    body="LGTM!",
    file_path="src/auth.py",
    line=17,
)

# Merge
merged = client.pull_requests.merge("myworkspace", "myrepo", 42, strategy="squash")
print(merged.state)  # "MERGED"
```

---

## Implementation Order

1. `exceptions.py` — no dependencies, foundation
2. `models.py` — no dependencies, all dataclasses
3. `auth.py` — depends on `requests`
4. `_http.py` — depends on `auth.py` and `exceptions.py`
5. `resources/repositories.py` — depends on `_http.py` and `models.py`
6. `resources/pull_requests.py` — depends on `_http.py` and `models.py`
7. `client.py` — wires everything together
8. `__init__.py` — public re-exports
9. `pyproject.toml` — package metadata
10. `tests/` — unit tests with mocked HTTP
