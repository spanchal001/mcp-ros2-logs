from __future__ import annotations

import os
from pathlib import Path
from typing import Literal


def resolve_log_path(log_dir: str | None = None) -> Path:
    """Resolve log root directory using the 5-level priority chain.

    1. log_dir parameter (explicit)
    2. MCP_ROS2_LOGS_DIR env var
    3. ROS_LOG_DIR env var
    4. $ROS_HOME/log/ if ROS_HOME set
    5. ~/.ros/log/ (default)
    """
    if log_dir is not None:
        return Path(log_dir).expanduser().resolve()

    env_mcp = os.environ.get("MCP_ROS2_LOGS_DIR")
    if env_mcp:
        return Path(env_mcp).expanduser().resolve()

    env_ros_log = os.environ.get("ROS_LOG_DIR")
    if env_ros_log:
        return Path(env_ros_log).expanduser().resolve()

    env_ros_home = os.environ.get("ROS_HOME")
    if env_ros_home:
        return Path(env_ros_home).expanduser().resolve() / "log"

    return Path.home() / ".ros" / "log"


def classify_path(path: Path) -> Literal["file", "run_dir", "bag_dir", "log_root"]:
    """Auto-detect what the path points to.

    - file: single .log file
    - run_dir: directory containing .log files directly
    - bag_dir: ROS2 bag directory (contains metadata.yaml)
    - log_root: directory containing run subdirectories
    """
    if path.is_file():
        return "file"

    if (path / "metadata.yaml").exists():
        return "bag_dir"

    if any(path.glob("*.log")):
        return "run_dir"

    return "log_root"
