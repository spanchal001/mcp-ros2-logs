from __future__ import annotations

from pathlib import Path

import pytest

from mcp_ros2_logs.parser import parse_run
from mcp_ros2_logs.query import get_node_summary

FIXTURES = Path(__file__).parent / "fixtures"
BAD_RUN = FIXTURES / "bad_run"
GOOD_RUN = FIXTURES / "good_run"


@pytest.fixture()
def bad_entries():
    return parse_run(BAD_RUN)


@pytest.fixture()
def good_entries():
    return parse_run(GOOD_RUN)


class TestSeverityCounts:
    def test_good_run_talker(self, good_entries) -> None:
        summary = get_node_summary(good_entries, "talker")
        assert summary is not None
        assert "INFO" in summary.severity_counts
        assert "DEBUG" in summary.severity_counts
        assert "ERROR" not in summary.severity_counts

    def test_bad_run_sensor_driver(self, bad_entries) -> None:
        summary = get_node_summary(bad_entries, "sensor_driver")
        assert summary is not None
        assert "ERROR" in summary.severity_counts
        assert "FATAL" in summary.severity_counts
        assert summary.severity_counts["ERROR"] > 0


class TestRecurringMessages:
    def test_talker_recurring(self, good_entries) -> None:
        summary = get_node_summary(good_entries, "talker")
        assert summary is not None
        assert len(summary.top_recurring) > 0
        # "Publishing: Hello World *" should be the top pattern
        top_pattern, top_count = summary.top_recurring[0]
        assert "Publishing" in top_pattern or "Hello" in top_pattern
        assert top_count > 5

    def test_max_five_recurring(self, good_entries) -> None:
        summary = get_node_summary(good_entries, "talker")
        assert summary is not None
        assert len(summary.top_recurring) <= 5

    def test_numbers_normalized(self, good_entries) -> None:
        summary = get_node_summary(good_entries, "talker")
        assert summary is not None
        # Normalized patterns should have * instead of specific numbers
        top_pattern = summary.top_recurring[0][0]
        assert "*" in top_pattern


class TestStackTraces:
    def test_motion_planner_has_stack_trace(self, bad_entries) -> None:
        summary = get_node_summary(bad_entries, "motion_planner")
        assert summary is not None
        assert len(summary.stack_traces) > 0
        trace_entry = summary.stack_traces[0]
        assert "Traceback" in trace_entry.message

    def test_good_run_no_stack_traces(self, good_entries) -> None:
        summary = get_node_summary(good_entries, "talker")
        assert summary is not None
        assert len(summary.stack_traces) == 0


class TestUniqueErrors:
    def test_sensor_driver_unique_errors(self, bad_entries) -> None:
        summary = get_node_summary(bad_entries, "sensor_driver")
        assert summary is not None
        assert len(summary.unique_errors) > 0
        # All should be ERROR or FATAL
        for e in summary.unique_errors:
            assert e.severity in ("ERROR", "FATAL")

    def test_unique_deduplication(self, bad_entries) -> None:
        """Repeated error messages with same text should be deduplicated."""
        summary = get_node_summary(bad_entries, "sensor_driver")
        assert summary is not None
        # "Reconnect failed" appears multiple times but should be deduplicated
        messages = [e.message.split("\n", 1)[0] for e in summary.unique_errors]
        assert len(messages) == len(set(messages))


class TestMessageRate:
    def test_positive_rate(self, good_entries) -> None:
        summary = get_node_summary(good_entries, "talker")
        assert summary is not None
        assert summary.message_rate > 0

    def test_uptime(self, good_entries) -> None:
        summary = get_node_summary(good_entries, "talker")
        assert summary is not None
        assert summary.uptime_seconds > 0
        assert summary.first_message_time < summary.last_message_time


class TestNonexistentNode:
    def test_returns_none(self, good_entries) -> None:
        summary = get_node_summary(good_entries, "nonexistent_node")
        assert summary is None
