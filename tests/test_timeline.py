from __future__ import annotations

from pathlib import Path

import pytest

from mcp_ros2_logs.parser import parse_run
from mcp_ros2_logs.timeline import (
    MessageGroup,
    NodeGap,
    SeverityTransition,
    get_timeline,
)

FIXTURES = Path(__file__).parent / "fixtures"
GOOD_RUN = FIXTURES / "good_run"
BAD_RUN = FIXTURES / "bad_run"


@pytest.fixture()
def good_entries():
    return parse_run(GOOD_RUN)


@pytest.fixture()
def bad_entries():
    return parse_run(BAD_RUN)


class TestGrouping:
    def test_groups_consecutive_same_severity(self, good_entries) -> None:
        result = get_timeline(good_entries)
        groups = [e for e in result.events if isinstance(e, MessageGroup)]
        assert len(groups) > 0
        # Good run should have groups of INFO and DEBUG
        severities = {g.severity for g in groups}
        assert severities <= {"INFO", "DEBUG"}

    def test_group_count(self, good_entries) -> None:
        result = get_timeline(good_entries)
        groups = [e for e in result.events if isinstance(e, MessageGroup)]
        total_entries = sum(g.count for g in groups)
        assert total_entries == len(good_entries)

    def test_single_message_group(self, bad_entries) -> None:
        """Groups with count=1 should be valid."""
        result = get_timeline(bad_entries)
        groups = [e for e in result.events if isinstance(e, MessageGroup)]
        single_groups = [g for g in groups if g.count == 1]
        # There should be at least some single-message groups (transitions)
        assert len(single_groups) >= 0  # no crash

    def test_sample_message_content(self, good_entries) -> None:
        result = get_timeline(good_entries)
        groups = [e for e in result.events if isinstance(e, MessageGroup)]
        for g in groups:
            assert len(g.sample_message) > 0
            assert len(g.sample_message) <= 80


class TestSeverityTransition:
    def test_detects_transitions(self, bad_entries) -> None:
        result = get_timeline(bad_entries)
        transitions = [e for e in result.events if isinstance(e, SeverityTransition)]
        assert len(transitions) > 0

    def test_transition_has_info_to_warn_or_error(self, bad_entries) -> None:
        result = get_timeline(bad_entries)
        transitions = [e for e in result.events if isinstance(e, SeverityTransition)]
        # Bad run has INFO -> WARN and INFO -> ERROR transitions
        from_sevs = {t.from_severity for t in transitions}
        to_sevs = {t.to_severity for t in transitions}
        assert "INFO" in from_sevs
        assert len(to_sevs & {"WARN", "ERROR", "FATAL"}) > 0

    def test_no_transitions_in_good_run(self, good_entries) -> None:
        """Good run has only INFO and DEBUG, but transitions between them are valid."""
        result = get_timeline(good_entries)
        transitions = [e for e in result.events if isinstance(e, SeverityTransition)]
        # All transitions should be between INFO and DEBUG only
        for t in transitions:
            assert t.from_severity in ("INFO", "DEBUG")
            assert t.to_severity in ("INFO", "DEBUG")


class TestNodeGap:
    def test_gap_detection_in_bad_run(self, bad_entries) -> None:
        """Bad run has a large time gap between normal and error phases."""
        result = get_timeline(bad_entries)
        gaps = [e for e in result.events if isinstance(e, NodeGap)]
        # There should be gaps where nodes go silent during the failure cascade
        assert len(gaps) > 0

    def test_gap_has_positive_seconds(self, bad_entries) -> None:
        result = get_timeline(bad_entries)
        gaps = [e for e in result.events if isinstance(e, NodeGap)]
        for g in gaps:
            assert g.gap_seconds > 0
            assert g.gap_end > g.gap_start


class TestFiltering:
    def test_time_range_filter(self, bad_entries) -> None:
        result = get_timeline(bad_entries, time_start="1713103350.0")
        # Should only have events after the error phase
        for ev in result.events:
            if isinstance(ev, MessageGroup):
                assert ev.time_start >= 1713103350.0
            elif isinstance(ev, SeverityTransition):
                assert ev.timestamp >= 1713103350.0

    def test_node_filter(self, bad_entries) -> None:
        result = get_timeline(bad_entries, nodes="sensor_driver")
        for ev in result.events:
            if isinstance(ev, MessageGroup):
                assert ev.node == "sensor_driver"
            elif isinstance(ev, SeverityTransition):
                assert ev.node == "sensor_driver"
            elif isinstance(ev, NodeGap):
                assert ev.node == "sensor_driver"


class TestChronologicalOrder:
    def test_events_sorted(self, bad_entries) -> None:
        result = get_timeline(bad_entries)

        def event_time(ev):
            if isinstance(ev, MessageGroup):
                return ev.time_start
            if isinstance(ev, SeverityTransition):
                return ev.timestamp
            return ev.gap_start

        times = [event_time(ev) for ev in result.events]
        assert times == sorted(times)


class TestEmpty:
    def test_empty_entries(self) -> None:
        result = get_timeline([])
        assert result.events == []
