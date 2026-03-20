from __future__ import annotations

import os


def get_default_limit() -> int:
    return int(os.environ.get("MCP_ROS2_LOGS_MAX_RESULTS", "100"))
