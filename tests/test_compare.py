from __future__ import annotations

from pathlib import Path

import pytest

from mcp_ros2_logs.compare import compare_runs
from mcp_ros2_logs.parser import parse_run

FIXTURES = Path(__file__).parent / "fixtures"
GOOD_RUN = FIXTURES / "good_run"
BAD_RUN = FIXTURES / "bad_run"


@pytest.fixture()
def good_entries():
    return parse_run(GOOD_RUN)


@pytest.fixture()
def bad_entries():
    return parse_run(BAD_RUN)


class TestNodeDifferences:
    def test_nodes_only_in_one_run(self, good_entries, bad_entries) -> None:
        result = compare_runs(good_entries, bad_entries)
        # good_run has: talker, listener, planner
        # bad_run has: sensor_driver, collision_checker, motion_planner
        assert len(result.nodes_only_in_1) > 0
        assert len(result.nodes_only_in_2) > 0

    def test_nodes_only_in_1_are_good_run_nodes(
        self, good_entries, bad_entries
    ) -> None:
        result = compare_runs(good_entries, bad_entries)
        for node in result.nodes_only_in_1:
            assert node in {"talker", "listener", "planner"}

    def test_nodes_only_in_2_are_bad_run_nodes(
        self, good_entries, bad_entries
    ) -> None:
        result = compare_runs(good_entries, bad_entries)
        for node in result.nodes_only_in_2:
            assert node in {"sensor_driver", "collision_checker", "motion_planner"}


class TestSeverityCounts:
    def test_same_run_common_nodes(self, good_entries) -> None:
        result = compare_runs(good_entries, good_entries)
        assert len(result.common_nodes) > 0
        for nc in result.common_nodes:
            assert nc.severity_counts_1 == nc.severity_counts_2


class TestNovelMessages:
    def test_novel_messages_detected(self, good_entries, bad_entries) -> None:
        result = compare_runs(good_entries, bad_entries)
        # bad_run has errors that don't exist in good_run
        assert len(result.novel_messages) > 0
        for e in result.novel_messages:
            assert e.severity in ("ERROR", "WARN", "FATAL")

    def test_no_novel_messages_same_run(self, good_entries) -> None:
        result = compare_runs(good_entries, good_entries)
        assert len(result.novel_messages) == 0

    def test_novel_messages_deduplicated(self, good_entries, bad_entries) -> None:
        """Same normalized template should appear only once in novel_messages."""
        result = compare_runs(good_entries, bad_entries)
        from mcp_ros2_logs.query import _normalize_message

        templates = [
            f"{e.node}::{_normalize_message(e.message)}"
            for e in result.novel_messages
        ]
        assert len(templates) == len(set(templates))


class TestFirstDivergence:
    def test_first_divergence_timestamp(self, good_entries, bad_entries) -> None:
        result = compare_runs(good_entries, bad_entries)
        assert result.first_divergence is not None
        # Should be the timestamp of the earliest novel error
        assert result.first_divergence == min(
            e.timestamp for e in result.novel_messages
        )

    def test_no_divergence_same_run(self, good_entries) -> None:
        result = compare_runs(good_entries, good_entries)
        assert result.first_divergence is None


class TestTimingDiffs:
    def test_timing_diffs_generated(self, good_entries, bad_entries) -> None:
        """Since good_run and bad_run have completely different nodes,
        there are no common nodes with errors to compare timing on."""
        result = compare_runs(good_entries, bad_entries)
        # No common nodes -> no timing diffs
        assert len(result.timing_diffs) == 0

    def test_timing_diffs_same_run_with_errors(self, bad_entries) -> None:
        """Comparing bad_run with itself: timing is identical, so no diffs."""
        result = compare_runs(bad_entries, bad_entries)
        for diff in result.timing_diffs:
            assert "delta: +0.0s" in diff


class TestEmpty:
    def test_empty_run_comparison(self, good_entries) -> None:
        result = compare_runs(good_entries, [])
        assert len(result.nodes_only_in_1) > 0
        assert len(result.nodes_only_in_2) == 0
        assert len(result.novel_messages) == 0

    def test_both_empty(self) -> None:
        result = compare_runs([], [])
        assert result.nodes_only_in_1 == []
        assert result.nodes_only_in_2 == []
        assert result.common_nodes == []
        assert result.novel_messages == []
        assert result.first_divergence is None
