from __future__ import annotations

from unittest.mock import patch

import pytest


class TestTransportDefaults:
    def test_default_is_stdio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_ROS2_LOGS_TRANSPORT", raising=False)
        monkeypatch.delenv("MCP_ROS2_LOGS_HOST", raising=False)
        monkeypatch.delenv("MCP_ROS2_LOGS_PORT", raising=False)

        with patch("mcp_ros2_logs.server.mcp") as mock_mcp:
            from mcp_ros2_logs.server import main

            with patch("sys.argv", ["mcp-ros2-logs"]):
                main()

            mock_mcp.run.assert_called_once_with(transport="stdio")

    def test_sse_sets_host_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_ROS2_LOGS_TRANSPORT", raising=False)
        monkeypatch.delenv("MCP_ROS2_LOGS_HOST", raising=False)
        monkeypatch.delenv("MCP_ROS2_LOGS_PORT", raising=False)

        with patch("mcp_ros2_logs.server.mcp") as mock_mcp:
            mock_mcp.settings = type("S", (), {"host": "127.0.0.1", "port": 8000})()
            from mcp_ros2_logs.server import main

            with patch("sys.argv", ["mcp-ros2-logs", "--transport", "sse", "--host", "0.0.0.0", "--port", "9000"]):
                main()

            assert mock_mcp.settings.host == "0.0.0.0"
            assert mock_mcp.settings.port == 9000
            mock_mcp.run.assert_called_once_with(transport="sse")

    def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ROS2_LOGS_TRANSPORT", "streamable-http")
        monkeypatch.setenv("MCP_ROS2_LOGS_HOST", "10.0.0.1")
        monkeypatch.setenv("MCP_ROS2_LOGS_PORT", "5000")

        with patch("mcp_ros2_logs.server.mcp") as mock_mcp:
            mock_mcp.settings = type("S", (), {"host": "127.0.0.1", "port": 8000})()
            from mcp_ros2_logs.server import main

            with patch("sys.argv", ["mcp-ros2-logs"]):
                main()

            assert mock_mcp.settings.host == "10.0.0.1"
            assert mock_mcp.settings.port == 5000
            mock_mcp.run.assert_called_once_with(transport="streamable-http")

    def test_invalid_transport_rejected(self) -> None:
        with patch("sys.argv", ["mcp-ros2-logs", "--transport", "websocket"]):
            with pytest.raises(SystemExit):
                from mcp_ros2_logs.server import main

                main()

    def test_stdio_does_not_set_host_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_ROS2_LOGS_TRANSPORT", raising=False)

        with patch("mcp_ros2_logs.server.mcp") as mock_mcp:
            mock_mcp.settings = type("S", (), {"host": "127.0.0.1", "port": 8000})()
            from mcp_ros2_logs.server import main

            with patch("sys.argv", ["mcp-ros2-logs"]):
                main()

            # host/port should remain unchanged for stdio
            assert mock_mcp.settings.host == "127.0.0.1"
            assert mock_mcp.settings.port == 8000
