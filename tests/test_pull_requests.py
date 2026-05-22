"""
Unit tests for PullRequestsResource.

All tests mock HTTPClient — no real network calls are made.
"""

import unittest
from unittest.mock import MagicMock, call

from bitbucket_sdk.resources.pull_requests import PullRequestsResource
from bitbucket_sdk.models import Comment, DiffStat, PagedList, PullRequest
from bitbucket_sdk.exceptions import NotFoundError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PR_DATA = {
    "id": 42,
    "title": "Fix the bug",
    "description": "Fixes #123",
    "state": "OPEN",
    "author": {"display_name": "Alice", "uuid": "{a}", "nickname": "alice", "account_id": "acc1"},
    "source": {"branch": {"name": "feature/fix"}, "repository": {"full_name": "ws/repo", "name": "repo", "uuid": "{r}", "scm": "git"}},
    "destination": {"branch": {"name": "main"}, "repository": {"full_name": "ws/repo", "name": "repo", "uuid": "{r}", "scm": "git"}},
    "close_source_branch": False,
    "created_on": "2024-01-15T10:00:00.000000+00:00",
    "updated_on": "2024-01-15T11:00:00.000000+00:00",
    "comment_count": 2,
    "task_count": 0,
    "reviewers": [],
    "participants": [],
}

_COMMENT_DATA = {
    "id": 99,
    "content": {"raw": "LGTM!", "markup": "markdown", "html": "<p>LGTM!</p>"},
    "user": {"display_name": "Bob", "uuid": "{b}", "nickname": "bob", "account_id": "acc2"},
    "created_on": "2024-01-15T12:00:00.000000+00:00",
    "updated_on": "2024-01-15T12:00:00.000000+00:00",
    "deleted": False,
    "resolution": None,
}

_INLINE_COMMENT_DATA = {
    **_COMMENT_DATA,
    "id": 100,
    "content": {"raw": "This line looks wrong", "markup": "markdown", "html": "<p>This line looks wrong</p>"},
    "inline": {"path": "src/auth.py", "to": 42},
    "resolution": None,
}

_RESOLVED_COMMENT_DATA = {
    **_COMMENT_DATA,
    "id": 101,
    "resolution": {"type": "resolved"},
}

_PR_PAGE = {
    "values": [_PR_DATA],
    "size": 1,
    "page": 1,
    "pagelen": 10,
}

_COMMENT_PAGE = {
    "values": [_COMMENT_DATA, _INLINE_COMMENT_DATA, _RESOLVED_COMMENT_DATA],
    "size": 3,
    "page": 1,
    "pagelen": 10,
}


def _make_resource():
    http = MagicMock()
    resource = PullRequestsResource(http)
    return resource, http


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

class TestList(unittest.TestCase):

    def test_list_calls_correct_path_with_state(self):
        resource, http = _make_resource()
        http.get.return_value = _PR_PAGE

        resource.list("ws", "repo")

        http.get.assert_called_once_with(
            "/repositories/ws/repo/pullrequests", params={"state": "OPEN"}
        )

    def test_list_custom_state(self):
        resource, http = _make_resource()
        http.get.return_value = {"values": [], "size": 0, "page": 1, "pagelen": 10}

        resource.list("ws", "repo", state="MERGED")

        http.get.assert_called_once_with(
            "/repositories/ws/repo/pullrequests", params={"state": "MERGED"}
        )

    def test_list_returns_paged_list_of_pull_requests(self):
        resource, http = _make_resource()
        http.get.return_value = _PR_PAGE

        result = resource.list("ws", "repo")

        self.assertIsInstance(result, PagedList)
        self.assertEqual(len(result), 1)
        pr = result.values[0]
        self.assertIsInstance(pr, PullRequest)
        self.assertEqual(pr.id, 42)
        self.assertEqual(pr.title, "Fix the bug")
        self.assertEqual(pr.source.branch_name, "feature/fix")
        self.assertEqual(pr.destination.branch_name, "main")


# ---------------------------------------------------------------------------
# get_open
# ---------------------------------------------------------------------------

class TestGetOpen(unittest.TestCase):

    def test_get_open_returns_first_open_pr_when_no_branch_given(self):
        resource, http = _make_resource()
        http.get.return_value = _PR_PAGE

        pr = resource.get_open("ws", "repo")

        self.assertEqual(pr.id, 42)

    def test_get_open_filters_by_branch(self):
        resource, http = _make_resource()
        http.get.return_value = _PR_PAGE

        pr = resource.get_open("ws", "repo", branch="feature/fix")

        self.assertEqual(pr.source.branch_name, "feature/fix")

    def test_get_open_raises_not_found_for_wrong_branch(self):
        resource, http = _make_resource()
        http.get.return_value = _PR_PAGE

        with self.assertRaises(NotFoundError):
            resource.get_open("ws", "repo", branch="nonexistent-branch")

    def test_get_open_raises_not_found_when_no_prs(self):
        resource, http = _make_resource()
        http.get.return_value = {"values": [], "size": 0, "page": 1, "pagelen": 10}

        with self.assertRaises(NotFoundError):
            resource.get_open("ws", "repo")


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

class TestGet(unittest.TestCase):

    def test_get_calls_correct_path(self):
        resource, http = _make_resource()
        http.get.return_value = _PR_DATA

        resource.get("ws", "repo", 42)

        http.get.assert_called_once_with("/repositories/ws/repo/pullrequests/42")

    def test_get_returns_pull_request(self):
        resource, http = _make_resource()
        http.get.return_value = _PR_DATA

        pr = resource.get("ws", "repo", 42)

        self.assertIsInstance(pr, PullRequest)
        self.assertEqual(pr.id, 42)
        self.assertEqual(pr.state, "OPEN")


# ---------------------------------------------------------------------------
# get_diff
# ---------------------------------------------------------------------------

class TestGetDiff(unittest.TestCase):

    def test_get_diff_calls_correct_path(self):
        resource, http = _make_resource()
        http.get_raw.return_value = "diff text"

        resource.get_diff("ws", "repo", 42)

        http.get_raw.assert_called_once_with("/repositories/ws/repo/pullrequests/42/diff")

    def test_get_diff_returns_string(self):
        resource, http = _make_resource()
        http.get_raw.return_value = "--- a/f.py\n+++ b/f.py\n"

        result = resource.get_diff("ws", "repo", 42)

        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# get_diffstat
# ---------------------------------------------------------------------------

class TestGetDiffstat(unittest.TestCase):

    def test_get_diffstat_calls_correct_path(self):
        resource, http = _make_resource()
        http.get.return_value = {
            "values": [
                {"status": "modified", "lines_added": 5, "lines_removed": 2,
                 "old": {"path": "src/a.py"}, "new": {"path": "src/a.py"}}
            ],
            "size": 1, "page": 1, "pagelen": 10,
        }

        resource.get_diffstat("ws", "repo", 42)

        http.get.assert_called_once_with("/repositories/ws/repo/pullrequests/42/diffstat")

    def test_get_diffstat_returns_paged_list_of_diff_stat(self):
        resource, http = _make_resource()
        http.get.return_value = {
            "values": [
                {"status": "added", "lines_added": 10, "lines_removed": 0,
                 "old": None, "new": {"path": "src/new.py"}},
            ],
            "size": 1, "page": 1, "pagelen": 10,
        }

        result = resource.get_diffstat("ws", "repo", 42)

        self.assertIsInstance(result, PagedList)
        self.assertIsInstance(result.values[0], DiffStat)
        self.assertEqual(result.values[0].status, "added")
        self.assertEqual(result.values[0].lines_added, 10)


# ---------------------------------------------------------------------------
# list_comments
# ---------------------------------------------------------------------------

class TestListComments(unittest.TestCase):

    def test_list_comments_calls_correct_path(self):
        resource, http = _make_resource()
        http.get.return_value = _COMMENT_PAGE

        resource.list_comments("ws", "repo", 42)

        http.get.assert_called_once_with("/repositories/ws/repo/pullrequests/42/comments")

    def test_list_comments_returns_paged_list_of_comments(self):
        resource, http = _make_resource()
        http.get.return_value = _COMMENT_PAGE

        result = resource.list_comments("ws", "repo", 42)

        self.assertIsInstance(result, PagedList)
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result.values[0], Comment)


# ---------------------------------------------------------------------------
# list_unresolved_comments
# ---------------------------------------------------------------------------

class TestListUnresolvedComments(unittest.TestCase):

    def test_filters_out_resolved_comments(self):
        resource, http = _make_resource()
        http.get.return_value = _COMMENT_PAGE  # 2 unresolved, 1 resolved

        result = resource.list_unresolved_comments("ws", "repo", 42)

        self.assertEqual(len(result), 2)
        for c in result:
            self.assertFalse(c.resolved)

    def test_inline_only_filters_to_inline_comments(self):
        resource, http = _make_resource()
        http.get.return_value = _COMMENT_PAGE  # 1 inline unresolved

        result = resource.list_unresolved_comments("ws", "repo", 42, inline_only=True)

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_inline)
        self.assertEqual(result[0].inline.path, "src/auth.py")  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# post_comment
# ---------------------------------------------------------------------------

class TestPostComment(unittest.TestCase):

    def test_post_general_comment(self):
        resource, http = _make_resource()
        http.post.return_value = _COMMENT_DATA

        resource.post_comment("ws", "repo", 42, "LGTM!")

        http.post.assert_called_once_with(
            "/repositories/ws/repo/pullrequests/42/comments",
            json={"content": {"raw": "LGTM!"}},
        )

    def test_post_inline_comment(self):
        resource, http = _make_resource()
        http.post.return_value = _INLINE_COMMENT_DATA

        resource.post_comment("ws", "repo", 42, "Bad line", file_path="src/auth.py", line=42)

        http.post.assert_called_once_with(
            "/repositories/ws/repo/pullrequests/42/comments",
            json={
                "content": {"raw": "Bad line"},
                "inline": {"path": "src/auth.py", "to": 42},
            },
        )

    def test_post_comment_returns_comment(self):
        resource, http = _make_resource()
        http.post.return_value = _COMMENT_DATA

        result = resource.post_comment("ws", "repo", 42, "LGTM!")

        self.assertIsInstance(result, Comment)
        self.assertEqual(result.content.raw, "LGTM!")

    def test_post_comment_raises_if_only_file_path_provided(self):
        resource, http = _make_resource()

        with self.assertRaises(ValueError):
            resource.post_comment("ws", "repo", 42, "comment", file_path="src/a.py")

    def test_post_comment_raises_if_only_line_provided(self):
        resource, http = _make_resource()

        with self.assertRaises(ValueError):
            resource.post_comment("ws", "repo", 42, "comment", line=10)


# ---------------------------------------------------------------------------
# resolve_comment
# ---------------------------------------------------------------------------

class TestResolveComment(unittest.TestCase):

    def test_resolve_comment_calls_correct_path(self):
        resource, http = _make_resource()
        http.post.return_value = None

        resource.resolve_comment("ws", "repo", 42, comment_id=99)

        http.post.assert_called_once_with(
            "/repositories/ws/repo/pullrequests/42/comments/99/resolve"
        )


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------

class TestApprove(unittest.TestCase):

    def test_approve_calls_correct_path(self):
        resource, http = _make_resource()
        http.post.return_value = None

        resource.approve("ws", "repo", 42)

        http.post.assert_called_once_with("/repositories/ws/repo/pullrequests/42/approve")


# ---------------------------------------------------------------------------
# decline
# ---------------------------------------------------------------------------

class TestDecline(unittest.TestCase):

    def test_decline_calls_correct_path(self):
        resource, http = _make_resource()
        declined_pr = {**_PR_DATA, "state": "DECLINED"}
        http.post.return_value = declined_pr

        result = resource.decline("ws", "repo", 42)

        http.post.assert_called_once_with("/repositories/ws/repo/pullrequests/42/decline")
        self.assertEqual(result.state, "DECLINED")


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

class TestMerge(unittest.TestCase):

    def test_merge_defaults_to_merge_commit_strategy(self):
        resource, http = _make_resource()
        merged_pr = {**_PR_DATA, "state": "MERGED"}
        http.post.return_value = merged_pr

        resource.merge("ws", "repo", 42)

        http.post.assert_called_once_with(
            "/repositories/ws/repo/pullrequests/42/merge",
            json={"merge_strategy": "merge_commit"},
        )

    def test_merge_with_squash_strategy(self):
        resource, http = _make_resource()
        http.post.return_value = {**_PR_DATA, "state": "MERGED"}

        resource.merge("ws", "repo", 42, strategy="squash")

        http.post.assert_called_once_with(
            "/repositories/ws/repo/pullrequests/42/merge",
            json={"merge_strategy": "squash"},
        )

    def test_merge_with_close_source_branch(self):
        resource, http = _make_resource()
        http.post.return_value = {**_PR_DATA, "state": "MERGED"}

        resource.merge("ws", "repo", 42, close_source_branch=True)

        payload = http.post.call_args.kwargs["json"]
        self.assertTrue(payload["close_source_branch"])

    def test_merge_with_message(self):
        resource, http = _make_resource()
        http.post.return_value = {**_PR_DATA, "state": "MERGED"}

        resource.merge("ws", "repo", 42, message="Squashed feature branch")

        payload = http.post.call_args.kwargs["json"]
        self.assertEqual(payload["message"], "Squashed feature branch")

    def test_merge_with_all_options(self):
        resource, http = _make_resource()
        http.post.return_value = {**_PR_DATA, "state": "MERGED"}

        resource.merge("ws", "repo", 42, strategy="squash", close_source_branch=True, message="Done")

        payload = http.post.call_args.kwargs["json"]
        self.assertEqual(payload["merge_strategy"], "squash")
        self.assertTrue(payload["close_source_branch"])
        self.assertEqual(payload["message"], "Done")

    def test_merge_omits_optional_fields_when_not_provided(self):
        resource, http = _make_resource()
        http.post.return_value = {**_PR_DATA, "state": "MERGED"}

        resource.merge("ws", "repo", 42)

        payload = http.post.call_args.kwargs["json"]
        self.assertNotIn("close_source_branch", payload)
        self.assertNotIn("message", payload)

    def test_merge_returns_pull_request(self):
        resource, http = _make_resource()
        http.post.return_value = {**_PR_DATA, "state": "MERGED"}

        result = resource.merge("ws", "repo", 42)

        self.assertIsInstance(result, PullRequest)
        self.assertEqual(result.state, "MERGED")


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

class TestCreate(unittest.TestCase):

    def test_create_calls_correct_path_and_payload(self):
        resource, http = _make_resource()
        http.post.return_value = _PR_DATA

        resource.create("ws", "repo", "My PR", "feature/x", "main")

        payload = http.post.call_args.kwargs["json"]
        self.assertEqual(payload["title"], "My PR")
        self.assertEqual(payload["source"]["branch"]["name"], "feature/x")
        self.assertEqual(payload["destination"]["branch"]["name"], "main")
        self.assertFalse(payload["close_source_branch"])

    def test_create_includes_description_when_provided(self):
        resource, http = _make_resource()
        http.post.return_value = _PR_DATA

        resource.create("ws", "repo", "My PR", "feature/x", "main", description="Fixes things")

        payload = http.post.call_args.kwargs["json"]
        self.assertEqual(payload["description"], "Fixes things")

    def test_create_with_reviewers(self):
        resource, http = _make_resource()
        http.post.return_value = _PR_DATA

        resource.create(
            "ws", "repo", "My PR", "feature/x", "main",
            reviewers=["{uuid-1}", "{uuid-2}"],
        )

        payload = http.post.call_args.kwargs["json"]
        self.assertEqual(payload["reviewers"], [{"uuid": "{uuid-1}"}, {"uuid": "{uuid-2}"}])

    def test_create_without_reviewers_omits_reviewers_field(self):
        resource, http = _make_resource()
        http.post.return_value = _PR_DATA

        resource.create("ws", "repo", "My PR", "feature/x", "main")

        payload = http.post.call_args.kwargs["json"]
        self.assertNotIn("reviewers", payload)

    def test_create_with_close_source_branch(self):
        resource, http = _make_resource()
        http.post.return_value = _PR_DATA

        resource.create("ws", "repo", "My PR", "feature/x", "main", close_source_branch=True)

        payload = http.post.call_args.kwargs["json"]
        self.assertTrue(payload["close_source_branch"])

    def test_create_returns_pull_request(self):
        resource, http = _make_resource()
        http.post.return_value = _PR_DATA

        result = resource.create("ws", "repo", "My PR", "feature/x", "main")

        self.assertIsInstance(result, PullRequest)
        self.assertEqual(result.title, "Fix the bug")


class TestUpdate(unittest.TestCase):

    def test_update_calls_put_with_correct_path(self):
        resource, http = _make_resource()
        http.put.return_value = _PR_DATA

        resource.update("ws", "repo", 42, title="New title")

        http.put.assert_called_once()
        args, kwargs = http.put.call_args
        self.assertEqual(args[0], "/repositories/ws/repo/pullrequests/42")

    def test_update_title_only(self):
        resource, http = _make_resource()
        http.put.return_value = _PR_DATA

        resource.update("ws", "repo", 42, title="Renamed")

        payload = http.put.call_args.kwargs["json"]
        self.assertEqual(payload, {"title": "Renamed"})

    def test_update_description_only(self):
        resource, http = _make_resource()
        http.put.return_value = _PR_DATA

        resource.update("ws", "repo", 42, description="A new body")

        payload = http.put.call_args.kwargs["json"]
        self.assertEqual(payload, {"description": "A new body"})

    def test_update_reviewers_replaces_list(self):
        resource, http = _make_resource()
        http.put.return_value = _PR_DATA

        resource.update("ws", "repo", 42, reviewers=["{uuid-1}", "{uuid-2}"])

        payload = http.put.call_args.kwargs["json"]
        self.assertEqual(payload, {"reviewers": [{"uuid": "{uuid-1}"}, {"uuid": "{uuid-2}"}]})

    def test_update_empty_reviewers_clears_list(self):
        """reviewers=[] is meaningful — it clears all reviewers."""
        resource, http = _make_resource()
        http.put.return_value = _PR_DATA

        resource.update("ws", "repo", 42, reviewers=[])

        payload = http.put.call_args.kwargs["json"]
        self.assertEqual(payload, {"reviewers": []})

    def test_update_omitting_reviewers_does_not_send_field(self):
        """reviewers=None must NOT appear in the payload (leave unchanged)."""
        resource, http = _make_resource()
        http.put.return_value = _PR_DATA

        resource.update("ws", "repo", 42, title="Just a title change")

        payload = http.put.call_args.kwargs["json"]
        self.assertNotIn("reviewers", payload)

    def test_update_destination_branch(self):
        resource, http = _make_resource()
        http.put.return_value = _PR_DATA

        resource.update("ws", "repo", 42, destination_branch="develop")

        payload = http.put.call_args.kwargs["json"]
        self.assertEqual(payload, {"destination": {"branch": {"name": "develop"}}})

    def test_update_close_source_branch(self):
        resource, http = _make_resource()
        http.put.return_value = _PR_DATA

        resource.update("ws", "repo", 42, close_source_branch=True)

        payload = http.put.call_args.kwargs["json"]
        self.assertEqual(payload, {"close_source_branch": True})

    def test_update_multiple_fields(self):
        resource, http = _make_resource()
        http.put.return_value = _PR_DATA

        resource.update(
            "ws", "repo", 42,
            title="New title",
            description="New body",
            close_source_branch=False,
        )

        payload = http.put.call_args.kwargs["json"]
        self.assertEqual(
            payload,
            {"title": "New title", "description": "New body", "close_source_branch": False},
        )

    def test_update_returns_pull_request(self):
        resource, http = _make_resource()
        http.put.return_value = _PR_DATA

        result = resource.update("ws", "repo", 42, title="x")

        self.assertIsInstance(result, PullRequest)
        self.assertEqual(result.id, 42)
        self.assertEqual(result.title, "Fix the bug")  # from _PR_DATA fixture

    def test_update_without_any_field_raises(self):
        resource, http = _make_resource()

        with self.assertRaises(ValueError) as ctx:
            resource.update("ws", "repo", 42)

        self.assertIn("at least one field", str(ctx.exception))
        http.put.assert_not_called()

    def test_update_requires_workspace(self):
        resource, http = _make_resource()

        with self.assertRaises(ValueError):
            resource.update("", "repo", 42, title="x")

        http.put.assert_not_called()

    def test_update_requires_repo(self):
        resource, http = _make_resource()

        with self.assertRaises(ValueError):
            resource.update("ws", "", 42, title="x")

        http.put.assert_not_called()


if __name__ == "__main__":
    unittest.main()
