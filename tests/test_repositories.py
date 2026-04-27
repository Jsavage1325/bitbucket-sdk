"""
Unit tests for RepositoriesResource.

All tests mock HTTPClient so no real network calls are made.
The pattern used here is the standard SDK testing approach:
  1. Create a mock HTTPClient
  2. Wire it into the resource under test
  3. Assert the resource calls the right path with the right params
  4. Assert the response is correctly parsed into model objects
"""

import unittest
from unittest.mock import MagicMock

from bitbucket_sdk.resources.repositories import RepositoriesResource
from bitbucket_sdk.models import Repository, PagedList


def _make_resource():
    """Return a RepositoriesResource backed by a mock HTTPClient."""
    http = MagicMock()
    resource = RepositoriesResource(http)
    return resource, http


class TestRepositoriesList(unittest.TestCase):

    def test_list_calls_correct_path(self):
        resource, http = _make_resource()
        http.get.return_value = {"values": [], "size": 0, "page": 1, "pagelen": 10}

        resource.list("myworkspace")

        http.get.assert_called_once_with("/repositories/myworkspace", params=None)

    def test_list_with_updated_since_passes_after_param(self):
        resource, http = _make_resource()
        http.get.return_value = {"values": [], "size": 0, "page": 1, "pagelen": 10}

        resource.list("myworkspace", updated_since="2024-01-01")

        http.get.assert_called_once_with(
            "/repositories/myworkspace", params={"after": "2024-01-01"}
        )

    def test_list_returns_paged_list_of_repositories(self):
        resource, http = _make_resource()
        http.get.return_value = {
            "values": [
                {"full_name": "myworkspace/repo-a", "name": "repo-a", "uuid": "{abc}", "scm": "git"},
                {"full_name": "myworkspace/repo-b", "name": "repo-b", "uuid": "{def}", "scm": "git"},
            ],
            "size": 2,
            "page": 1,
            "pagelen": 10,
            "next": None,
        }

        result = resource.list("myworkspace")

        self.assertIsInstance(result, PagedList)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result.values[0], Repository)
        self.assertEqual(result.values[0].full_name, "myworkspace/repo-a")
        self.assertEqual(result.values[1].name, "repo-b")

    def test_list_is_iterable(self):
        resource, http = _make_resource()
        http.get.return_value = {
            "values": [{"full_name": "ws/repo", "name": "repo", "uuid": "{x}", "scm": "git"}],
            "size": 1,
            "page": 1,
            "pagelen": 10,
        }

        names = [r.full_name for r in resource.list("ws")]

        self.assertEqual(names, ["ws/repo"])

    def test_list_preserves_pagination_metadata(self):
        resource, http = _make_resource()
        http.get.return_value = {
            "values": [],
            "size": 50,
            "page": 2,
            "pagelen": 10,
            "next": "https://api.bitbucket.org/2.0/repositories/ws?page=3",
            "previous": "https://api.bitbucket.org/2.0/repositories/ws?page=1",
        }

        result = resource.list("ws")

        self.assertEqual(result.size, 50)
        self.assertEqual(result.page, 2)
        self.assertIsNotNone(result.next)
        self.assertIsNotNone(result.previous)


class TestRepositoriesGetCommitDiff(unittest.TestCase):

    def test_get_commit_diff_calls_correct_path(self):
        resource, http = _make_resource()
        http.get_raw.return_value = "--- a/foo.py\n+++ b/foo.py\n"

        resource.get_commit_diff("ws", "myrepo", "abc1234")

        http.get_raw.assert_called_once_with("/repositories/ws/myrepo/diff/abc1234")

    def test_get_commit_diff_with_range(self):
        resource, http = _make_resource()
        http.get_raw.return_value = "diff output"

        result = resource.get_commit_diff("ws", "myrepo", "abc1234..def5678")

        http.get_raw.assert_called_once_with("/repositories/ws/myrepo/diff/abc1234..def5678")
        self.assertEqual(result, "diff output")

    def test_get_commit_diff_returns_string(self):
        resource, http = _make_resource()
        expected = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n"
        http.get_raw.return_value = expected

        result = resource.get_commit_diff("ws", "repo", "sha123")

        self.assertIsInstance(result, str)
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
