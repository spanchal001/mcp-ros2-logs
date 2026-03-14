from __future__ import annotations

from pathlib import Path

import pytest

from mcp_ros2_logs.parser import parse_run
from mcp_ros2_logs.query import query_logs

FIXTURES = Path(__file__).parent / "fixtures"
BAD_RUN = FIXTURES / "bad_run"
GOOD_RUN = FIXTURES / "good_run"


@pytest.fixture()
def bad_entries():
    return parse_run(BAD_RUN)


@pytest.fixture()
def good_entries():
    return parse_run(GOOD_RUN)


class TestSeverityFilter:
    def test_single_severity(self, bad_entries) -> None:
        result = query_logs(bad_entries, severity="ERROR")
        assert result.total_matches > 0
        assert all(e.severity == "ERROR" for e in result.matches)

    def test_multiple_severity_string(self, bad_entries) -> None:
        result = query_logs(bad_entries, severity="ERROR,FATAL")
        severities = {e.severity for e in result.matches}
        assert severities <= {"ERROR", "FATAL"}
        assert "ERROR" in severities
        assert "FATAL" in severities

    def test_multiple_severity_list(self, bad_entries) -> None:
        result = query_logs(bad_entries, severity=["WARN", "ERROR"])
        severities = {e.severity for e in result.matches}
        assert severities <= {"WARN", "ERROR"}

    def test_no_matches(self, good_entries) -> None:
        result = query_logs(good_entries, severity="FATAL")
        assert result.total_matches == 0
        assert result.matches == []


class TestNodeFilter:
    def test_single_node(self, bad_entries) -> None:
        result = query_logs(bad_entries, nodes="sensor_driver")
        assert result.total_matches > 0
        assert all(e.node == "sensor_driver" for e in result.matches)

    def test_multiple_nodes_string(self, bad_entries) -> None:
        result = query_logs(bad_entries, nodes="sensor_driver,collision_checker")
        nodes = {e.node for e in result.matches}
        assert nodes <= {"sensor_driver", "collision_checker"}
        assert len(nodes) == 2

    def test_multiple_nodes_list(self, bad_entries) -> None:
        result = query_logs(bad_entries, nodes=["sensor_driver", "motion_planner"])
        nodes = {e.node for e in result.matches}
        assert nodes <= {"sensor_driver", "motion_planner"}


class TestTimeFilter:
    def test_absolute_epoch(self, bad_entries) -> None:
        result = query_logs(
            bad_entries, time_start="1713103351.0", time_end="1713103352.0"
        )
        assert result.total_matches > 0
        for e in result.matches:
            assert 1713103351.0 <= e.timestamp <= 1713103352.0

    def test_relative_negative(self, bad_entries) -> None:
        """'-5s' = 5 seconds before run end."""
        result = query_logs(bad_entries, time_start="-5s")
        run_end = bad_entries[-1].timestamp
        for e in result.matches:
            assert e.timestamp >= run_end - 5.0

    def test_relative_positive(self, bad_entries) -> None:
        """'+5s' = 5 seconds after run start."""
        result = query_logs(bad_entries, time_end="+5s")
        run_start = bad_entries[0].timestamp
        for e in result.matches:
            assert e.timestamp <= run_start + 5.0

    def test_iso_format(self, bad_entries) -> None:
        result = query_logs(
            bad_entries,
            time_start="2024-04-14T14:02:31",
            time_end="2024-04-14T14:02:33",
        )
        assert result.total_matches > 0


class TestTextFilter:
    def test_substring(self, bad_entries) -> None:
        result = query_logs(bad_entries, text="timeout")
        assert result.total_matches > 0
        for e in result.matches:
            assert "timeout" in e.message.lower()

    def test_regex(self, bad_entries) -> None:
        result = query_logs(bad_entries, text="reconnect.*\\(\\d+/\\d+\\)")
        assert result.total_matches > 0
        for e in result.matches:
            assert "reconnect" in e.message.lower()

    def test_no_text_match(self, good_entries) -> None:
        result = query_logs(good_entries, text="NONEXISTENT_STRING_XYZ")
        assert result.total_matches == 0


class TestLimit:
    def test_limit_truncation(self, good_entries) -> None:
        result = query_logs(good_entries, limit=5)
        assert len(result.matches) == 5
        assert result.total_matches == len(good_entries)
        assert result.truncated is True

    def test_limit_not_exceeded(self, good_entries) -> None:
        result = query_logs(good_entries, limit=1000)
        assert len(result.matches) == len(good_entries)
        assert result.truncated is False


class TestContext:
    def test_context_includes_surrounding(self, bad_entries) -> None:
        """Context should include messages from ALL nodes around the match."""
        result_no_ctx = query_logs(bad_entries, severity="FATAL", context=0)
        result_ctx = query_logs(bad_entries, severity="FATAL", context=3)
        assert len(result_ctx.matches) > len(result_no_ctx.matches)

    def test_context_cross_node(self, bad_entries) -> None:
        """Context should include entries from other nodes."""
        result = query_logs(bad_entries, severity="FATAL", nodes="motion_planner", context=5)
        nodes_in_context = {e.node for e in result.matches}
        # Should include entries from other nodes in the context window
        assert len(nodes_in_context) > 1

    def test_context_no_duplicates(self, bad_entries) -> None:
        """Overlapping context windows should be merged without duplicates."""
        result = query_logs(bad_entries, severity="ERROR", context=3)
        # Check no duplicate (timestamp, node, line_number) tuples
        keys = [(e.timestamp, e.node, e.line_number) for e in result.matches]
        assert len(keys) == len(set(keys))

    def test_context_preserves_total_matches(self, bad_entries) -> None:
        """total_matches should reflect actual filter matches, not context entries."""
        result_no_ctx = query_logs(bad_entries, severity="ERROR")
        result_ctx = query_logs(bad_entries, severity="ERROR", context=3)
        assert result_ctx.total_matches == result_no_ctx.total_matches


class TestCombinedFilters:
    def test_severity_and_node(self, bad_entries) -> None:
        result = query_logs(bad_entries, severity="ERROR", nodes="sensor_driver")
        assert result.total_matches > 0
        for e in result.matches:
            assert e.severity == "ERROR"
            assert e.node == "sensor_driver"

    def test_severity_and_time(self, bad_entries) -> None:
        result = query_logs(
            bad_entries, severity="ERROR", time_start="1713103351.0"
        )
        assert result.total_matches > 0
        for e in result.matches:
            assert e.severity == "ERROR"
            assert e.timestamp >= 1713103351.0

    def test_all_filters(self, bad_entries) -> None:
        result = query_logs(
            bad_entries,
            severity="ERROR",
            nodes="sensor_driver",
            time_start="1713103351.0",
            text="timeout",
        )
        assert result.total_matches > 0
        for e in result.matches:
            assert e.severity == "ERROR"
            assert e.node == "sensor_driver"
            assert "timeout" in e.message.lower()


class TestEmptyEntries:
    def test_empty_list(self) -> None:
        result = query_logs([], severity="ERROR")
        assert result.total_matches == 0
        assert result.matches == []
        assert result.truncated is False
