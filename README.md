# bitbucket-sdk

Python SDK for the Bitbucket Cloud REST API v2.0.

## Installation

```bash
pip install -e .
```

## Authentication

Two authentication methods are supported.

### Option 1 — Atlassian API token (most common)

```bash
export BITBUCKET_EMAIL="you@example.com"
export BITBUCKET_API_TOKEN="ATATxxxxxxxxxxxxxxx"
```

Generate a token at: https://id.atlassian.com/manage-profile/security/api-tokens

```python
client = BitbucketClient()                                           # reads env vars
client = BitbucketClient(email="you@example.com", api_token="...") # explicit
```

### Option 2 — OAuth 2.0 / workspace access token (Bearer Auth)

Use this when you already hold an access token — e.g. from CI/CD, a Bitbucket
workspace access token, or a completed OAuth flow.

```bash
export BITBUCKET_ACCESS_TOKEN="eyJxxxxxxxxxxxxxxx"
```

```python
client = BitbucketClient()                       # reads BITBUCKET_ACCESS_TOKEN from env
client = BitbucketClient(access_token="eyJ...") # explicit
```

**Auth resolution:** if `access_token` (or `BITBUCKET_ACCESS_TOKEN`) is present it
takes precedence over API token credentials.

---

## Quick start

```python
from bitbucket_sdk import BitbucketClient

# Reads BITBUCKET_EMAIL and BITBUCKET_API_TOKEN from environment
client = BitbucketClient()

# Use as a context manager to close the connection pool cleanly on exit
with BitbucketClient() as client:
    repos = client.repositories.list("myworkspace")
    for repo in repos:
        print(repo.full_name)
```

---

## API Reference

### `BitbucketClient`

```python
client = BitbucketClient(
    email=None,       # falls back to BITBUCKET_EMAIL env var
    api_token=None,   # falls back to BITBUCKET_API_TOKEN env var
    timeout=30,       # HTTP request timeout in seconds
)
```

Supports use as a context manager (`with BitbucketClient() as client:`), which closes
the underlying connection pool on exit.

Sub-resources:
- `client.repositories` → `RepositoriesResource`
- `client.pull_requests` → `PullRequestsResource`

---

### `client.repositories`

#### `list(workspace, updated_since=None)` → `PagedList[Repository]`

List repositories in a workspace (first page only). Use `list_all()` for all pages.

```python
repos = client.repositories.list("myworkspace")
repos = client.repositories.list("myworkspace", updated_since="2024-01-01")
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workspace` | `str` | yes | Workspace slug |
| `updated_since` | `str` | no | ISO-8601 date — only return repos updated after this date |

---

#### `list_all(workspace, updated_since=None)` → `Iterator[Repository]`

Yield every repository across all pages automatically.

```python
for repo in client.repositories.list_all("myworkspace"):
    print(repo.full_name)
```

---

#### `get_commit_diff(workspace, repo, commits)` → `str`

Raw unified diff for a commit or commit range.

```python
diff = client.repositories.get_commit_diff("myworkspace", "myrepo", "abc1234")
diff = client.repositories.get_commit_diff("myworkspace", "myrepo", "abc1234..def5678")
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workspace` | `str` | yes | Workspace slug |
| `repo` | `str` | yes | Repository slug |
| `commits` | `str` | yes | Single hash (`"abc1234"`) or range (`"abc..def"`) |

---

### `client.pull_requests`

#### `list(workspace, repo, state="OPEN")` → `PagedList[PullRequest]`

List pull requests filtered by state (first page only). Use `list_all()` for all pages.

```python
open_prs   = client.pull_requests.list("myworkspace", "myrepo")
merged_prs = client.pull_requests.list("myworkspace", "myrepo", state="MERGED")
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workspace` | `str` | yes | Workspace slug |
| `repo` | `str` | yes | Repository slug |
| `state` | `str` | no | `"OPEN"` (default), `"MERGED"`, `"DECLINED"`, `"SUPERSEDED"` |

---

#### `list_all(workspace, repo, state="OPEN")` → `Iterator[PullRequest]`

Yield every pull request across all pages automatically.

```python
for pr in client.pull_requests.list_all("myworkspace", "myrepo"):
    print(pr.id, pr.title)
```

---

#### `get_open(workspace, repo, branch=None)` → `PullRequest`

Return a single open PR, optionally filtered by source branch name.
Raises `NotFoundError` if no match is found.

```python
pr = client.pull_requests.get_open("myworkspace", "myrepo")
pr = client.pull_requests.get_open("myworkspace", "myrepo", branch="feature/my-thing")
```

---

#### `get(workspace, repo, pr_id)` → `PullRequest`

Fetch a single pull request by its numeric ID.

```python
pr = client.pull_requests.get("myworkspace", "myrepo", 42)
print(pr.title, pr.state, pr.author.display_name)
```

---

#### `get_diff(workspace, repo, pr_id)` → `str`

Raw unified diff for a pull request.

```python
diff = client.pull_requests.get_diff("myworkspace", "myrepo", 42)
```

---

#### `get_diffstat(workspace, repo, pr_id)` → `PagedList[DiffStat]`

Per-file change statistics for a pull request.

```python
stats = client.pull_requests.get_diffstat("myworkspace", "myrepo", 42)
for stat in stats:
    print(stat.new_path, f"+{stat.lines_added} -{stat.lines_removed}")
```

`DiffStat` fields: `status`, `lines_added`, `lines_removed`, `old_path`, `new_path`

---

#### `list_comments(workspace, repo, pr_id)` → `PagedList[Comment]`

List all comments on a PR (first page only). Use `list_all_comments()` for all pages.

```python
comments = client.pull_requests.list_comments("myworkspace", "myrepo", 42)
```

---

#### `list_all_comments(workspace, repo, pr_id)` → `Iterator[Comment]`

Yield every comment across all pages automatically.

```python
for comment in client.pull_requests.list_all_comments("myworkspace", "myrepo", 42):
    print(comment.user.display_name, comment.content.raw)
```

---

#### `list_unresolved_comments(workspace, repo, pr_id, inline_only=False)` → `list[Comment]`

Return only unresolved comments. Fetches all pages internally.

```python
unresolved = client.pull_requests.list_unresolved_comments("myworkspace", "myrepo", 42)

# Only unresolved inline (file-attached) comments
inline = client.pull_requests.list_unresolved_comments("myworkspace", "myrepo", 42, inline_only=True)
for c in inline:
    print(c.inline.path, c.inline.to_line, c.content.raw)
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `inline_only` | `bool` | no | If `True`, only return inline comments (default `False`) |

---

#### `post_comment(workspace, repo, pr_id, body, file_path=None, line=None)` → `Comment`

Post a comment on a PR. Provide `file_path` **and** `line` together for an inline comment.

```python
# General comment
comment = client.pull_requests.post_comment("myworkspace", "myrepo", 42, "LGTM!")

# Inline comment on a specific file and line
comment = client.pull_requests.post_comment(
    "myworkspace", "myrepo", 42,
    body="This looks suspicious.",
    file_path="src/auth.py",
    line=17,
)
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `body` | `str` | yes | Comment text (Markdown supported) |
| `file_path` | `str` | no | File path — must be paired with `line` |
| `line` | `int` | no | Line number (1-based) — must be paired with `file_path` |

---

#### `resolve_comment(workspace, repo, pr_id, comment_id)` → `None`

Mark an inline comment thread as resolved.

```python
client.pull_requests.resolve_comment("myworkspace", "myrepo", 42, comment_id=99)
```

---

#### `approve(workspace, repo, pr_id)` → `None`

Approve a PR as the authenticated user.

```python
client.pull_requests.approve("myworkspace", "myrepo", 42)
```

---

#### `unapprove(workspace, repo, pr_id)` → `None`

Remove the authenticated user's approval from a PR.

```python
client.pull_requests.unapprove("myworkspace", "myrepo", 42)
```

---

#### `decline(workspace, repo, pr_id)` → `PullRequest`

Decline a PR.

```python
pr = client.pull_requests.decline("myworkspace", "myrepo", 42)
print(pr.state)  # "DECLINED"
```

---

#### `merge(workspace, repo, pr_id, strategy="merge_commit", close_source_branch=None, message=None)` → `PullRequest`

Merge a PR.

```python
pr = client.pull_requests.merge("myworkspace", "myrepo", 42)
pr = client.pull_requests.merge("myworkspace", "myrepo", 42, strategy="squash")
pr = client.pull_requests.merge("myworkspace", "myrepo", 42, close_source_branch=True, message="Done")
print(pr.state)  # "MERGED"
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `strategy` | `str` | no | `"merge_commit"` (default), `"squash"`, `"fast_forward"` |
| `close_source_branch` | `bool` | no | Delete source branch after merge. Defaults to the PR's own setting |
| `message` | `str` | no | Custom merge commit message |

---

#### `create(workspace, repo, title, source_branch, destination_branch, description=None, reviewers=None, close_source_branch=False)` → `PullRequest`

Create a new pull request.

```python
pr = client.pull_requests.create(
    workspace="myworkspace",
    repo="myrepo",
    title="Add login page",
    source_branch="feature/login",
    destination_branch="main",
    description="Implements the login flow from the spec.",
    reviewers=["{uuid-abc}", "{uuid-def}"],  # Bitbucket user UUIDs
    close_source_branch=True,
)
print(pr.id, pr.title)
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | `str` | yes | PR title |
| `source_branch` | `str` | yes | Branch containing the changes |
| `destination_branch` | `str` | yes | Branch to merge into |
| `description` | `str` | no | PR description (Markdown supported) |
| `reviewers` | `list[str]` | no | List of reviewer UUIDs (find via Bitbucket UI or API) |
| `close_source_branch` | `bool` | no | Delete source branch after merge (default `False`) |

---

## Response Models

### `PullRequest`
| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | PR number |
| `title` | `str` | PR title |
| `description` | `str` | PR description |
| `state` | `str` | `"OPEN"`, `"MERGED"`, `"DECLINED"`, `"SUPERSEDED"` |
| `author` | `User` | Author details |
| `source` | `Ref` | Source branch (`source.branch_name`) |
| `destination` | `Ref` | Destination branch (`destination.branch_name`) |
| `comment_count` | `int` | Total comments |
| `created_on` | `datetime` | Creation timestamp |
| `updated_on` | `datetime` | Last updated timestamp |

### `Comment`
| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Comment ID |
| `content` | `Content` | Body (`content.raw` for Markdown text) |
| `user` | `User` | Author |
| `inline` | `Inline \| None` | Inline location if applicable |
| `resolved` | `bool` | Whether the thread is resolved |
| `is_inline` | `bool` | Property — `True` if this is an inline comment |

### `Repository`
| Field | Type | Description |
|-------|------|-------------|
| `full_name` | `str` | `"workspace/repo"` |
| `name` | `str` | Repo slug |
| `uuid` | `str` | Unique identifier |
| `scm` | `str` | `"git"` |

### `PagedList[T]`
Returned by all list methods. Iterable and supports `len()`.

| Field | Type | Description |
|-------|------|-------------|
| `values` | `list[T]` | Items on this page |
| `size` | `int` | Total items across all pages |
| `page` | `int` | Current page number |
| `next` | `str \| None` | URL for the next page |

Use the corresponding `list_all()` / `list_all_comments()` methods to iterate all pages
without manually following `next`.

---

## Error Handling

```python
from bitbucket_sdk import (
    BitbucketClient,
    AuthenticationError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    APIError,
    BitbucketError,
)

try:
    pr = client.pull_requests.get("myworkspace", "myrepo", 999)
except NotFoundError:
    print("PR does not exist")
except AuthenticationError:
    print("Invalid credentials — check BITBUCKET_EMAIL and BITBUCKET_API_TOKEN")
except PermissionError:
    print("You do not have access to this resource")
except RateLimitError:
    print("Rate limited — the SDK retries this automatically")
except APIError as e:
    print(f"Unexpected API error: {e.status_code} {e}")
except BitbucketError as e:
    print(f"SDK error: {e}")
```

---

## Retry Behaviour

The SDK automatically retries transient failures using **tenacity**:

| Trigger | Behaviour |
|---------|-----------|
| Network error (connection reset, timeout) | Retry with exponential backoff |
| HTTP 429 with `Retry-After` header | Wait the exact duration the server requests |
| HTTP 429 without `Retry-After` | Retry with exponential backoff |
| HTTP 5xx server errors | Retry with exponential backoff |
| HTTP 400 / 401 / 403 / 404 | Raise immediately — these are caller errors |

Policy: up to **3 attempts**, backoff sequence 1s → 2s → 4s (capped at 10s).
Retry attempts are logged at `WARNING` level via Python's standard `logging` module.

To see retry logs:

```python
import logging
logging.basicConfig(level=logging.WARNING)
```

---

## Logging

The SDK logs at two levels using the `bitbucket_sdk._http` logger:

| Level | What is logged |
|-------|---------------|
| `DEBUG` | Every request (`--> GET /path`) and response (`<-- 200`) |
| `WARNING` | Each retry attempt before sleeping |

```python
import logging
logging.getLogger("bitbucket_sdk._http").setLevel(logging.DEBUG)
```
