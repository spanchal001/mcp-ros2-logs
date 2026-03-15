from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_ros2_logs.server import (
    resource_errors,
    resource_list_runs,
    resource_node_summary,
    resource_run_summary,
    resource_timeline,
    store,
)

FIXTURES = Path(__file__).parent / "fixtures"
GOOD_RUN = FIXTURES / "good_run"
BAD_RUN = FIXTURES / "bad_run"


class TestResourceListRuns:
    def test_returns_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ROS2_LOGS_DIR", str(FIXTURES))
        result = resource_list_runs()
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0


class TestResourceRunSummary:
    def test_returns_run_info(self) -> None:
        store.load("good_run", str(FIXTURES))
        result = resource_run_summary("good_run")
        data = json.loads(result)
        assert data["run_id"] == "good_run"
        assert "nodes" in data
        assert "severity_counts" in data
        assert data["num_entries"] == 75


class TestResourceNodeSummary:
    def test_returns_formatted_text(self) -> None:
        store.load("good_run", str(FIXTURES))
        result = resource_node_summary("good_run", "talker")
        assert "Node: talker" in result
        assert "Uptime:" in result
        assert "Severity counts:" in result

    def test_node_not_found(self) -> None:
        store.load("good_run", str(FIXTURES))
        result = resource_node_summary("good_run", "nonexistent")
        assert "not found" in result


class TestResourceTimeline:
    def test_returns_formatted_text(self) -> None:
        store.load("bad_run", str(FIXTURES))
        result = resource_timeline("bad_run")
        assert len(result) > 0
        assert "No events found." not in result


class TestResourceErrors:
    def test_returns_errors(self) -> None:
        store.load("bad_run", str(FIXTURES))
        result = resource_errors("bad_run")
        assert "Total errors:" in result
        assert "ERROR" in result

    def test_no_errors_in_good_run(self) -> None:
        store.load("good_run", str(FIXTURES))
        result = resource_errors("good_run")
        assert "Total errors: 0" in result
