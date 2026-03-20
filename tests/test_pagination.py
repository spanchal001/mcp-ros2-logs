from __future__ import annotations

from pathlib import Path

import pytest

from mcp_ros2_logs.config import get_default_limit
from mcp_ros2_logs.parser import parse_run
from mcp_ros2_logs.query import query_logs
from mcp_ros2_logs.server import _paginate

FIXTURES = Path(__file__).parent / "fixtures"
BAD_RUN = FIXTURES / "bad_run"


@pytest.fixture()
def bad_entries():
    return parse_run(BAD_RUN)


class TestGetDefaultLimit:
    def test_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_ROS2_LOGS_MAX_RESULTS", raising=False)
        assert get_default_limit() == 100

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ROS2_LOGS_MAX_RESULTS", "25")
        assert get_default_limit() == 25


class TestPaginateHelper:
    def test_no_truncation(self) -> None:
        items = list(range(5))
        page, total, notice = _paginate(items, limit=10, offset=0)
        assert page == items
        assert total == 5
        assert notice == ""

    def test_limit_truncation(self) -> None:
        items = list(range(20))
        page, total, notice = _paginate(items, limit=5, offset=0)
        assert page == [0, 1, 2, 3, 4]
        assert total == 20
        assert "Showing 5 of 20" in notice
        assert "offset=5" in notice

    def test_offset(self) -> None:
        items = list(range(20))
        page, total, notice = _paginate(items, limit=5, offset=5)
        assert page == [5, 6, 7, 8, 9]
        assert total == 20
        assert "offset 5" in notice
        assert "offset=10" in notice

    def test_offset_at_end(self) -> None:
        items = list(range(10))
        page, total, notice = _paginate(items, limit=5, offset=5)
        assert page == [5, 6, 7, 8, 9]
        assert total == 10
        assert "Showing 5 of 10" in notice
        # No "Use offset=..." since we're at the end
        assert "Use offset=" not in notice

    def test_offset_beyond_end(self) -> None:
        items = list(range(5))
        page, total, notice = _paginate(items, limit=10, offset=100)
        assert page == []
        assert total == 5


class TestQueryLogsOffset:
    def test_offset_skips_entries(self, bad_entries) -> None:
        full = query_logs(bad_entries, limit=10, offset=0)
        offset = query_logs(bad_entries, limit=10, offset=5)
        # The first entry with offset=5 should be the 6th entry from offset=0
        assert offset.matches[0] == full.matches[5]

    def test_offset_preserves_total(self, bad_entries) -> None:
        full = query_logs(bad_entries, limit=1000)
        offset = query_logs(bad_entries, limit=5, offset=10)
        assert offset.total_matches == full.total_matches

    def test_offset_truncated(self, bad_entries) -> None:
        total = len(bad_entries)
        result = query_logs(bad_entries, limit=5, offset=0)
        assert result.truncated is True
        # Near the end — not truncated
        result = query_logs(bad_entries, limit=1000, offset=total - 1)
        assert result.truncated is False

    def test_offset_with_severity_filter(self, bad_entries) -> None:
        all_errors = query_logs(bad_entries, severity="ERROR", limit=1000)
        page = query_logs(bad_entries, severity="ERROR", limit=3, offset=2)
        assert page.total_matches == all_errors.total_matches
        assert page.matches[0] == all_errors.matches[2]
