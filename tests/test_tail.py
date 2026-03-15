from __future__ import annotations

from pathlib import Path

from mcp_ros2_logs.tail import TailWatcher


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n")


def _append_log(path: Path, lines: list[str]) -> None:
    with path.open("a") as f:
        f.write("\n".join(lines) + "\n")


class TestTailWatcher:
    def test_initialize_records_positions(self, tmp_path: Path) -> None:
        log_file = tmp_path / "node.log"
        _write_log(log_file, [
            "[INFO] [1713103320.000000000] [talker]: Hello",
            "[INFO] [1713103321.000000000] [talker]: World",
        ])
        watcher = TailWatcher()
        watcher.initialize("run1", tmp_path)
        assert watcher.has_state("run1")

    def test_no_updates_without_changes(self, tmp_path: Path) -> None:
        log_file = tmp_path / "node.log"
        _write_log(log_file, [
            "[INFO] [1713103320.000000000] [talker]: Hello",
        ])
        watcher = TailWatcher()
        watcher.initialize("run1", tmp_path)
        new = watcher.check_updates(tmp_path, "run1")
        assert new == []

    def test_detects_new_entries(self, tmp_path: Path) -> None:
        log_file = tmp_path / "node.log"
        _write_log(log_file, [
            "[INFO] [1713103320.000000000] [talker]: Hello",
        ])
        watcher = TailWatcher()
        watcher.initialize("run1", tmp_path)

        _append_log(log_file, [
            "[INFO] [1713103321.000000000] [talker]: World",
            "[ERROR] [1713103322.000000000] [talker]: Fail",
        ])
        new = watcher.check_updates(tmp_path, "run1")
        assert len(new) == 2
        assert new[0].message == "World"
        assert new[1].severity == "ERROR"

    def test_multiple_tail_calls(self, tmp_path: Path) -> None:
        log_file = tmp_path / "node.log"
        _write_log(log_file, [
            "[INFO] [1713103320.000000000] [talker]: Initial",
        ])
        watcher = TailWatcher()
        watcher.initialize("run1", tmp_path)

        # First append
        _append_log(log_file, [
            "[INFO] [1713103321.000000000] [talker]: Second",
        ])
        new1 = watcher.check_updates(tmp_path, "run1")
        assert len(new1) == 1

        # Second append
        _append_log(log_file, [
            "[INFO] [1713103322.000000000] [talker]: Third",
        ])
        new2 = watcher.check_updates(tmp_path, "run1")
        assert len(new2) == 1
        assert new2[0].message == "Third"

    def test_new_file_detected(self, tmp_path: Path) -> None:
        log_file = tmp_path / "node1.log"
        _write_log(log_file, [
            "[INFO] [1713103320.000000000] [talker]: Hello",
        ])
        watcher = TailWatcher()
        watcher.initialize("run1", tmp_path)

        # Add a new log file
        log_file2 = tmp_path / "node2.log"
        _write_log(log_file2, [
            "[ERROR] [1713103321.000000000] [listener]: Error",
        ])
        new = watcher.check_updates(tmp_path, "run1")
        assert len(new) == 1
        assert new[0].node == "listener"

    def test_single_file_mode(self, tmp_path: Path) -> None:
        log_file = tmp_path / "output.log"
        _write_log(log_file, [
            "[INFO] [1713103320.000000000] [talker]: Hello",
        ])
        watcher = TailWatcher()
        watcher.initialize("run1", log_file)

        _append_log(log_file, [
            "[INFO] [1713103321.000000000] [talker]: New",
        ])
        new = watcher.check_updates(log_file, "run1")
        assert len(new) == 1

    def test_no_state_returns_empty(self, tmp_path: Path) -> None:
        watcher = TailWatcher()
        new = watcher.check_updates(tmp_path, "nonexistent")
        assert new == []

    def test_has_state(self, tmp_path: Path) -> None:
        watcher = TailWatcher()
        assert not watcher.has_state("run1")
        log_file = tmp_path / "node.log"
        _write_log(log_file, [
            "[INFO] [1713103320.000000000] [talker]: Hello",
        ])
        watcher.initialize("run1", tmp_path)
        assert watcher.has_state("run1")
