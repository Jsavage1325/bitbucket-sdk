"""
Unit tests for PipelinesResource.

All tests mock HTTPClient — no real network calls.
Matches the pattern in test_repositories.py / test_pull_requests.py.
"""

import unittest
from unittest.mock import MagicMock

from bitbucket_sdk.models import PagedList, Pipeline, PipelineStep, TestCase
from bitbucket_sdk.resources.pipelines import PipelinesResource


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PIPELINE_DATA = {
    "uuid": "{p1}",
    "build_number": 42,
    "state": {"name": "COMPLETED", "result": {"name": "SUCCESSFUL"}},
    "target": {
        "ref_type": "branch",
        "ref_name": "main",
        "commit": {"hash": "abc1234"},
    },
    "created_on": "2026-01-15T10:00:00.000000+00:00",
    "completed_on": "2026-01-15T10:08:00.000000+00:00",
    "duration_in_seconds": 480,
    "creator": {"display_name": "Alice"},
}

_PIPELINE_FAILED = {
    **_PIPELINE_DATA,
    "uuid": "{p2}",
    "build_number": 43,
    "state": {"name": "COMPLETED", "result": {"name": "FAILED"}},
}

_PIPELINE_IN_PROGRESS = {
    "uuid": "{p3}",
    "build_number": 44,
    "state": {"name": "IN_PROGRESS"},
    "target": {"ref_type": "branch", "ref_name": "develop", "commit": {"hash": "def5678"}},
    "created_on": "2026-01-15T11:00:00.000000+00:00",
    "completed_on": None,
    "duration_in_seconds": 0,
    "creator": {"display_name": "Bob"},
}

_STEP_DATA = {
    "uuid": "{s1}",
    "name": "Build",
    "state": {"name": "COMPLETED", "result": {"name": "SUCCESSFUL"}},
    "started_on": "2026-01-15T10:00:30.000000+00:00",
    "completed_on": "2026-01-15T10:05:00.000000+00:00",
    "duration_in_seconds": 270,
}

_TEST_CASE_DATA = {
    "name": "test_foo",
    "status": "PASSED",
    "duration_in_ms": 1234,
    "package_name": "myapp.tests",
    "class_name": "TestFoo",
    "fully_qualified_name": "myapp.tests.TestFoo.test_foo",
}

_TEST_CASE_FAILED = {**_TEST_CASE_DATA, "name": "test_bar", "status": "FAILED"}


def _make_resource():
    http = MagicMock()
    return PipelinesResource(http), http


# ---------------------------------------------------------------------------
# list / list_all
# ---------------------------------------------------------------------------


class TestPipelinesList(unittest.TestCase):

    def test_list_uses_sort_newest_first_and_default_pagelen(self):
        resource, http = _make_resource()
        http.get.return_value = {"values": [], "size": 0, "page": 1, "pagelen": 10}

        resource.list("ws", "repo")

        http.get.assert_called_once_with(
            "/repositories/ws/repo/pipelines/",
            params={"sort": "-created_on", "pagelen": 10},
        )

    def test_list_filters_by_ref_and_status(self):
        resource, http = _make_resource()
        http.get.return_value = {"values": [], "size": 0, "page": 1, "pagelen": 5}

        resource.list("ws", "repo", ref="main", status="FAILED", page_size=5)

        http.get.assert_called_once_with(
            "/repositories/ws/repo/pipelines/",
            params={
                "sort": "-created_on",
                "pagelen": 5,
                "target.ref_name": "main",
                "status": "FAILED",
            },
        )

    def test_list_returns_paged_list_of_pipelines(self):
        resource, http = _make_resource()
        http.get.return_value = {
            "values": [_PIPELINE_DATA, _PIPELINE_FAILED],
            "size": 2,
            "page": 1,
            "pagelen": 10,
        }

        result = resource.list("ws", "repo")

        self.assertIsInstance(result, PagedList)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result.values[0], Pipeline)
        self.assertEqual(result.values[0].build_number, 42)
        self.assertEqual(result.values[0].state, "COMPLETED")
        self.assertEqual(result.values[0].result, "SUCCESSFUL")
        self.assertTrue(result.values[0].is_successful)
        self.assertFalse(result.values[1].is_successful)

    def test_list_handles_in_flight_pipeline_with_no_result(self):
        resource, http = _make_resource()
        http.get.return_value = {
            "values": [_PIPELINE_IN_PROGRESS],
            "size": 1,
            "page": 1,
            "pagelen": 10,
        }

        result = resource.list("ws", "repo")

        self.assertEqual(result.values[0].state, "IN_PROGRESS")
        self.assertEqual(result.values[0].result, "")
        self.assertFalse(result.values[0].is_finished)
        self.assertIsNone(result.values[0].completed_on)


class TestPipelinesListAll(unittest.TestCase):

    def test_list_all_uses_max_page_size_and_follows_next(self):
        resource, http = _make_resource()
        http.get.return_value = {
            "values": [_PIPELINE_DATA],
            "size": 2,
            "page": 1,
            "pagelen": 100,
            "next": "https://api.bitbucket.org/2.0/repositories/ws/repo/pipelines/?page=2",
        }
        http.get_next_page.return_value = {
            "values": [_PIPELINE_FAILED],
            "size": 2,
            "page": 2,
            "pagelen": 100,
        }

        result = list(resource.list_all("ws", "repo"))

        # First call goes via list() which sets pagelen=100
        first_call = http.get.call_args
        self.assertEqual(first_call.kwargs["params"]["pagelen"], 100)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].build_number, 42)
        self.assertEqual(result[1].build_number, 43)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


class TestPipelinesGet(unittest.TestCase):

    def test_get_returns_pipeline(self):
        resource, http = _make_resource()
        http.get.return_value = _PIPELINE_DATA

        result = resource.get("ws", "repo", "{p1}")

        http.get.assert_called_once_with("/repositories/ws/repo/pipelines/{p1}")
        self.assertIsInstance(result, Pipeline)
        self.assertEqual(result.uuid, "{p1}")
        self.assertEqual(result.ref_name, "main")
        self.assertEqual(result.commit_hash, "abc1234")


# ---------------------------------------------------------------------------
# list_steps
# ---------------------------------------------------------------------------


class TestPipelinesListSteps(unittest.TestCase):

    def test_list_steps_returns_paged_list_of_steps(self):
        resource, http = _make_resource()
        http.get.return_value = {
            "values": [_STEP_DATA],
            "size": 1,
            "page": 1,
            "pagelen": 10,
        }

        result = resource.list_steps("ws", "repo", "{p1}")

        http.get.assert_called_once_with("/repositories/ws/repo/pipelines/{p1}/steps/")
        self.assertIsInstance(result, PagedList)
        self.assertIsInstance(result.values[0], PipelineStep)
        self.assertEqual(result.values[0].name, "Build")
        self.assertEqual(result.values[0].state, "COMPLETED")
        self.assertEqual(result.values[0].result, "SUCCESSFUL")


# ---------------------------------------------------------------------------
# get_step_log
# ---------------------------------------------------------------------------


class TestPipelinesGetStepLog(unittest.TestCase):

    def test_get_step_log_returns_full_log_by_default(self):
        resource, http = _make_resource()
        http.get_raw.return_value = "line1\nline2\nline3\n"

        result = resource.get_step_log("ws", "repo", "{p1}", "{s1}")

        http.get_raw.assert_called_once_with(
            "/repositories/ws/repo/pipelines/{p1}/steps/{s1}/log"
        )
        self.assertEqual(result, "line1\nline2\nline3\n")

    def test_get_step_log_tail_lines_slices_to_last_n(self):
        resource, http = _make_resource()
        http.get_raw.return_value = "\n".join(f"line{i}" for i in range(1, 11))

        result = resource.get_step_log("ws", "repo", "{p1}", "{s1}", tail_lines=3)

        self.assertEqual(result, "line8\nline9\nline10")

    def test_get_step_log_tail_lines_zero_returns_full_log(self):
        resource, http = _make_resource()
        http.get_raw.return_value = "full log"

        result = resource.get_step_log("ws", "repo", "{p1}", "{s1}", tail_lines=0)

        self.assertEqual(result, "full log")

    def test_get_step_log_tail_lines_larger_than_log_returns_whole_log(self):
        resource, http = _make_resource()
        http.get_raw.return_value = "only\ntwo\nlines"

        result = resource.get_step_log("ws", "repo", "{p1}", "{s1}", tail_lines=100)

        self.assertEqual(result, "only\ntwo\nlines")


# ---------------------------------------------------------------------------
# list_test_cases
# ---------------------------------------------------------------------------


class TestPipelinesListTestCases(unittest.TestCase):

    def test_list_test_cases_returns_paged_list(self):
        resource, http = _make_resource()
        http.get.return_value = {
            "values": [_TEST_CASE_DATA, _TEST_CASE_FAILED],
            "size": 2,
            "page": 1,
            "pagelen": 100,
        }

        result = resource.list_test_cases("ws", "repo", "{p1}", "{s1}")

        http.get.assert_called_once_with(
            "/repositories/ws/repo/pipelines/{p1}/steps/{s1}/test_reports/test_cases/"
        )
        self.assertIsInstance(result, PagedList)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result.values[0], TestCase)
        self.assertEqual(result.values[0].name, "test_foo")
        self.assertFalse(result.values[0].is_failure)
        self.assertTrue(result.values[1].is_failure)

    def test_list_test_cases_empty_when_step_published_no_reports(self):
        resource, http = _make_resource()
        http.get.return_value = {"values": [], "size": 0, "page": 1, "pagelen": 100}

        result = resource.list_test_cases("ws", "repo", "{p1}", "{s1}")

        self.assertEqual(len(result), 0)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestPipelinesValidation(unittest.TestCase):

    def test_list_requires_workspace(self):
        resource, _ = _make_resource()
        with self.assertRaises(ValueError):
            resource.list("", "repo")

    def test_get_requires_pipeline_uuid(self):
        resource, _ = _make_resource()
        with self.assertRaises(ValueError):
            resource.get("ws", "repo", "")

    def test_get_step_log_requires_step_uuid(self):
        resource, _ = _make_resource()
        with self.assertRaises(ValueError):
            resource.get_step_log("ws", "repo", "{p1}", "")

    def test_list_test_cases_requires_step_uuid(self):
        resource, _ = _make_resource()
        with self.assertRaises(ValueError):
            resource.list_test_cases("ws", "repo", "{p1}", "")


if __name__ == "__main__":
    unittest.main()
