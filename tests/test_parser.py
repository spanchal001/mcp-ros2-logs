from __future__ import annotations

from pathlib import Path

import pytest

from mcp_ros2_logs.parser import parse_log_file, parse_run

FIXTURES = Path(__file__).parent / "fixtures"
GOOD_RUN = FIXTURES / "good_run"
BAD_RUN = FIXTURES / "bad_run"
SINGLE_FILE = FIXTURES / "single_file" / "console_output.log"


class TestParseGoodRun:
    def test_talker_entry_count(self) -> None:
        entries = parse_log_file(GOOD_RUN / "talker_12345_20240414-140200.log")
        assert len(entries) == 26

    def test_listener_entry_count(self) -> None:
        entries = parse_log_file(GOOD_RUN / "listener_12346_20240414-140200.log")
        assert len(entries) == 25

    def test_planner_entry_count(self) -> None:
        entries = parse_log_file(GOOD_RUN / "planner_12347_20240414-140200.log")
        assert len(entries) == 24

    def test_only_info_and_debug(self) -> None:
        for log_file in GOOD_RUN.glob("*.log"):
            entries = parse_log_file(log_file)
            severities = {e.severity for e in entries}
            assert severities <= {"INFO", "DEBUG"}, f"Unexpected severities in {log_file.name}"

    def test_timestamps_non_decreasing(self) -> None:
        for log_file in GOOD_RUN.glob("*.log"):
            entries = parse_log_file(log_file)
            for i in range(1, len(entries)):
                assert entries[i].timestamp >= entries[i - 1].timestamp


class TestParseBadRun:
    def test_sensor_driver_has_errors(self) -> None:
        entries = parse_log_file(BAD_RUN / "sensor_driver_12345_20240414-140200.log")
        severities = {e.severity for e in entries}
        assert "ERROR" in severities
        assert "FATAL" in severities
        assert "WARN" in severities

    def test_collision_checker_has_errors(self) -> None:
        entries = parse_log_file(
            BAD_RUN / "collision_checker_12346_20240414-140200.log"
        )
        severities = {e.severity for e in entries}
        assert "ERROR" in severities

    def test_motion_planner_has_fatal(self) -> None:
        entries = parse_log_file(
            BAD_RUN / "motion_planner_12347_20240414-140200.log"
        )
        severities = {e.severity for e in entries}
        assert "FATAL" in severities

    def test_multiline_stack_trace(self) -> None:
        entries = parse_log_file(
            BAD_RUN / "motion_planner_12347_20240414-140200.log"
        )
        fatal_entries = [e for e in entries if e.severity == "FATAL"]
        assert len(fatal_entries) == 1
        fatal = fatal_entries[0]
        assert "Traceback (most recent call last):" in fatal.message
        assert "TimeoutError: Collision checker service unavailable" in fatal.message
        assert "\n" in fatal.message

    def test_multiline_preserves_lines(self) -> None:
        entries = parse_log_file(
            BAD_RUN / "motion_planner_12347_20240414-140200.log"
        )
        fatal = [e for e in entries if e.severity == "FATAL"][0]
        lines = fatal.message.split("\n")
        # First line is the message, then 8 traceback lines
        assert len(lines) == 9

    def test_entry_after_multiline(self) -> None:
        """Verify the ERROR after the stack trace is parsed as a separate entry."""
        entries = parse_log_file(
            BAD_RUN / "motion_planner_12347_20240414-140200.log"
        )
        # Last entry should be the ERROR after the traceback
        last = entries[-1]
        assert last.severity == "ERROR"
        assert "Emergency stop" in last.message


class TestParseSingleFile:
    def test_entry_count(self) -> None:
        entries = parse_log_file(SINGLE_FILE)
        assert len(entries) == 19

    def test_interleaved_nodes(self) -> None:
        entries = parse_log_file(SINGLE_FILE)
        nodes = {e.node for e in entries}
        assert nodes == {"talker", "listener", "planner"}

    def test_source_file(self) -> None:
        entries = parse_log_file(SINGLE_FILE)
        assert all(e.source_file == "console_output.log" for e in entries)


class TestParseRun:
    def test_merges_and_sorts(self) -> None:
        entries = parse_run(GOOD_RUN)
        assert len(entries) > 0
        # Verify sorted by timestamp
        for i in range(1, len(entries)):
            assert entries[i].timestamp >= entries[i - 1].timestamp

    def test_multiple_source_files(self) -> None:
        entries = parse_run(GOOD_RUN)
        source_files = {e.source_file for e in entries}
        assert len(source_files) == 3

    def test_total_entry_count(self) -> None:
        entries = parse_run(GOOD_RUN)
        # 26 + 25 + 24 = 75
        assert len(entries) == 75


class TestEdgeCases:
    def test_skip_unparseable_prefix(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "Some garbage line\n"
            "Another garbage line\n"
            "[INFO] [1713103320.000000000] [test_node]: Valid message\n"
            "[INFO] [1713103321.000000000] [test_node]: Another valid message\n"
        )
        entries = parse_log_file(log_file)
        assert len(entries) == 2
        assert entries[0].message == "Valid message"
        assert entries[0].line_number == 3

    def test_empty_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "empty.log"
        log_file.write_text("")
        entries = parse_log_file(log_file)
        assert entries == []

    def test_line_numbers_correct(self) -> None:
        entries = parse_log_file(GOOD_RUN / "talker_12345_20240414-140200.log")
        assert entries[0].line_number == 1
        assert entries[1].line_number == 2

    def test_source_file_is_basename(self) -> None:
        entries = parse_log_file(GOOD_RUN / "talker_12345_20240414-140200.log")
        assert entries[0].source_file == "talker_12345_20240414-140200.log"

    def test_timestamp_precision(self) -> None:
        entries = parse_log_file(GOOD_RUN / "talker_12345_20240414-140200.log")
        # First entry: 1713103320.000000000
        assert entries[0].timestamp == pytest.approx(1713103320.0)
