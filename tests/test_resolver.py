from __future__ import annotations

from pathlib import Path

import pytest

from mcp_ros2_logs.resolver import classify_path, resolve_log_path

FIXTURES = Path(__file__).parent / "fixtures"

# Clear all relevant env vars for each test
ENV_VARS = ["MCP_ROS2_LOGS_DIR", "ROS_LOG_DIR", "ROS_HOME"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)


class TestResolveLogPath:
    def test_explicit_arg_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ROS2_LOGS_DIR", "/should/not/use")
        monkeypatch.setenv("ROS_LOG_DIR", "/should/not/use")
        result = resolve_log_path("/tmp/explicit")
        assert result == Path("/tmp/explicit")

    def test_mcp_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ROS2_LOGS_DIR", "/tmp/mcp_logs")
        result = resolve_log_path()
        assert result == Path("/tmp/mcp_logs")

    def test_ros_log_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ROS_LOG_DIR", "/tmp/ros_logs")
        result = resolve_log_path()
        assert result == Path("/tmp/ros_logs")

    def test_ros_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ROS_HOME", "/tmp/ros_home")
        result = resolve_log_path()
        assert result == Path("/tmp/ros_home/log")

    def test_default_fallback(self) -> None:
        result = resolve_log_path()
        assert result == Path.home() / ".ros" / "log"

    def test_priority_mcp_over_ros_log_dir(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MCP_ROS2_LOGS_DIR", "/tmp/mcp")
        monkeypatch.setenv("ROS_LOG_DIR", "/tmp/ros")
        result = resolve_log_path()
        assert result == Path("/tmp/mcp")

    def test_priority_ros_log_dir_over_ros_home(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROS_LOG_DIR", "/tmp/ros_log")
        monkeypatch.setenv("ROS_HOME", "/tmp/ros_home")
        result = resolve_log_path()
        assert result == Path("/tmp/ros_log")

    def test_tilde_expansion(self) -> None:
        result = resolve_log_path("~/my_logs")
        assert result == Path.home() / "my_logs"


class TestClassifyPath:
    def test_classify_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.log"
        f.write_text("content")
        assert classify_path(f) == "file"

    def test_classify_run_dir(self, tmp_path: Path) -> None:
        (tmp_path / "node1.log").write_text("content")
        (tmp_path / "node2.log").write_text("content")
        assert classify_path(tmp_path) == "run_dir"

    def test_classify_log_root(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run_2024_04_14"
        run_dir.mkdir()
        (run_dir / "node.log").write_text("content")
        assert classify_path(tmp_path) == "log_root"

    def test_classify_empty_dir_as_log_root(self, tmp_path: Path) -> None:
        # Empty dir has no .log files -> log_root
        assert classify_path(tmp_path) == "log_root"

    def test_classify_fixtures_good_run(self) -> None:
        assert classify_path(FIXTURES / "good_run") == "run_dir"

    def test_classify_fixtures_root(self) -> None:
        assert classify_path(FIXTURES) == "log_root"
