from __future__ import annotations

from pathlib import Path

import pytest

from mcp_ros2_logs.store import LogStore, RunInfo

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def store() -> LogStore:
    return LogStore()


class TestListRuns:
    def test_list_from_log_root(self, store: LogStore) -> None:
        summaries = store.list_runs(str(FIXTURES))
        run_ids = {s.run_id for s in summaries}
        assert "good_run" in run_ids
        assert "bad_run" in run_ids
        assert "single_file" in run_ids

    def test_list_from_run_dir(self, store: LogStore) -> None:
        summaries = store.list_runs(str(FIXTURES / "good_run"))
        assert len(summaries) == 1
        assert summaries[0].run_id == "good_run"
        assert summaries[0].num_files == 3

    def test_summary_has_line_counts(self, store: LogStore) -> None:
        summaries = store.list_runs(str(FIXTURES / "good_run"))
        assert summaries[0].total_lines > 0


class TestLoadRun:
    def test_load_good_run(self, store: LogStore) -> None:
        info = store.load("good_run", str(FIXTURES))
        assert isinstance(info, RunInfo)
        assert len(info.entries) == 75
        assert set(info.nodes) == {"talker", "listener", "planner"}

    def test_load_bad_run(self, store: LogStore) -> None:
        info = store.load("bad_run", str(FIXTURES))
        assert "ERROR" in info.severity_counts
        assert "FATAL" in info.severity_counts

    def test_load_severity_counts(self, store: LogStore) -> None:
        info = store.load("good_run", str(FIXTURES))
        assert "INFO" in info.severity_counts
        assert "DEBUG" in info.severity_counts
        total = sum(info.severity_counts.values())
        assert total == 75

    def test_load_time_range(self, store: LogStore) -> None:
        info = store.load("good_run", str(FIXTURES))
        start, end = info.time_range
        assert start < end
        assert start == pytest.approx(1713103320.0)

    def test_cache_hit(self, store: LogStore) -> None:
        info1 = store.load("good_run", str(FIXTURES))
        info2 = store.load("good_run", str(FIXTURES))
        assert info1 is info2

    def test_load_missing_run(self, store: LogStore) -> None:
        with pytest.raises(FileNotFoundError):
            store.load("nonexistent_run", str(FIXTURES))

    def test_get_before_load(self, store: LogStore) -> None:
        assert store.get("good_run") is None

    def test_get_after_load(self, store: LogStore) -> None:
        store.load("good_run", str(FIXTURES))
        info = store.get("good_run")
        assert info is not None
        assert info.summary.run_id == "good_run"
