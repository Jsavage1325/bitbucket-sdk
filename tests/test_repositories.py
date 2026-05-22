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
from bitbucket_sdk.models import Repository, PagedList, SrcEntry
from bitbucket_sdk.exceptions import NotFoundError


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


class TestRepositoriesGetFile(unittest.TestCase):

    def test_get_file_with_explicit_ref(self):
        resource, http = _make_resource()
        http.get_raw.return_value = "file contents here"

        result = resource.get_file("ws", "repo", "src/main.py", ref="develop")

        http.get_raw.assert_called_once_with("/repositories/ws/repo/src/develop/src/main.py")
        self.assertEqual(result, "file contents here")

    def test_get_file_strips_leading_slash_in_path(self):
        resource, http = _make_resource()
        http.get_raw.return_value = ""

        resource.get_file("ws", "repo", "/src/main.py", ref="develop")

        http.get_raw.assert_called_once_with("/repositories/ws/repo/src/develop/src/main.py")

    def test_get_file_looks_up_default_branch_when_ref_is_none(self):
        resource, http = _make_resource()
        # First call resolves the default branch; second fetches the file.
        http.get.return_value = {"mainbranch": {"name": "main"}}
        http.get_raw.return_value = "content"

        resource.get_file("ws", "repo", "README.md")

        http.get.assert_called_once_with("/repositories/ws/repo")
        http.get_raw.assert_called_once_with("/repositories/ws/repo/src/main/README.md")

    def test_get_file_raises_when_default_branch_unknown(self):
        resource, http = _make_resource()
        http.get.return_value = {}  # no mainbranch field

        with self.assertRaises(NotFoundError):
            resource.get_file("ws", "repo", "README.md")

        http.get_raw.assert_not_called()

    def test_get_file_requires_path(self):
        resource, http = _make_resource()

        with self.assertRaises(ValueError):
            resource.get_file("ws", "repo", "", ref="main")

        http.get_raw.assert_not_called()


class TestRepositoriesListDirectory(unittest.TestCase):

    def test_list_directory_calls_meta_endpoint(self):
        resource, http = _make_resource()
        http.get.return_value = {"values": [], "size": 0, "page": 1, "pagelen": 10}

        resource.list_directory("ws", "repo", "src", ref="develop")

        # Single call — directly passes through, no main-branch lookup needed.
        http.get.assert_called_once_with(
            "/repositories/ws/repo/src/develop/src",
            params={"format": "meta"},
        )

    def test_list_directory_defaults_path_to_root(self):
        resource, http = _make_resource()
        http.get.return_value = {"values": [], "size": 0, "page": 1, "pagelen": 10}

        resource.list_directory("ws", "repo", ref="develop")

        http.get.assert_called_once_with(
            "/repositories/ws/repo/src/develop/",
            params={"format": "meta"},
        )

    def test_list_directory_strips_leading_slash(self):
        resource, http = _make_resource()
        http.get.return_value = {"values": [], "size": 0, "page": 1, "pagelen": 10}

        resource.list_directory("ws", "repo", "/src/lib", ref="develop")

        http.get.assert_called_once_with(
            "/repositories/ws/repo/src/develop/src/lib",
            params={"format": "meta"},
        )

    def test_list_directory_looks_up_default_branch_when_ref_is_none(self):
        resource, http = _make_resource()
        http.get.side_effect = [
            {"mainbranch": {"name": "main"}},  # repo lookup for default branch
            {"values": [], "size": 0, "page": 1, "pagelen": 10},  # actual dir listing
        ]

        resource.list_directory("ws", "repo", "src")

        self.assertEqual(http.get.call_count, 2)
        self.assertEqual(http.get.call_args_list[0][0], ("/repositories/ws/repo",))
        self.assertEqual(
            http.get.call_args_list[1][0], ("/repositories/ws/repo/src/main/src",)
        )

    def test_list_directory_returns_paged_list_of_src_entries(self):
        resource, http = _make_resource()
        http.get.return_value = {
            "values": [
                {"type": "commit_directory", "path": "src/lib"},
                {"type": "commit_file", "path": "src/main.py", "size": 1234},
            ],
            "size": 2,
            "page": 1,
            "pagelen": 10,
        }

        result = resource.list_directory("ws", "repo", "src", ref="develop")

        self.assertIsInstance(result, PagedList)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result.values[0], SrcEntry)
        self.assertTrue(result.values[0].is_directory)
        self.assertEqual(result.values[0].path, "src/lib")
        self.assertTrue(result.values[1].is_file)
        self.assertEqual(result.values[1].size, 1234)


if __name__ == "__main__":
    unittest.main()
