from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mcp_ros2_logs.bag import BagInfo, parse_bag


def _create_bag_fixture(bag_dir: Path) -> None:
    """Create a minimal ROS2 bag directory with metadata.yaml and a .db3 file."""
    bag_dir.mkdir(parents=True, exist_ok=True)

    # Create metadata.yaml
    metadata = {
        "rosbag2_bagfile_information": {
            "version": 5,
            "storage_identifier": "sqlite3",
            "relative_file_paths": ["test_0.db3"],
            "duration": {"nanoseconds": 5_000_000_000},
            "starting_time": {"nanoseconds_since_epoch": 1713103320_000_000_000},
            "message_count": 6,
            "topics_with_message_count": [
                {
                    "topic_metadata": {
                        "name": "/scan",
                        "type": "sensor_msgs/msg/LaserScan",
                        "serialization_format": "cdr",
                    },
                    "message_count": 3,
                },
                {
                    "topic_metadata": {
                        "name": "/cmd_vel",
                        "type": "geometry_msgs/msg/Twist",
                        "serialization_format": "cdr",
                    },
                    "message_count": 3,
                },
            ],
        }
    }
    from ruamel.yaml import YAML
    yaml = YAML()
    with (bag_dir / "metadata.yaml").open("w") as f:
        yaml.dump(metadata, f)

    # Create .db3 SQLite file with rosbag2 schema
    db_path = bag_dir / "test_0.db3"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE topics ("
        "  id INTEGER PRIMARY KEY,"
        "  name TEXT NOT NULL,"
        "  type TEXT NOT NULL,"
        "  serialization_format TEXT NOT NULL,"
        "  offered_qos_profiles TEXT NOT NULL DEFAULT ''"
        ")"
    )
    conn.execute(
        "CREATE TABLE messages ("
        "  id INTEGER PRIMARY KEY,"
        "  topic_id INTEGER NOT NULL,"
        "  timestamp INTEGER NOT NULL,"
        "  data BLOB NOT NULL"
        ")"
    )

    conn.execute(
        "INSERT INTO topics (id, name, type, serialization_format) "
        "VALUES (1, '/scan', 'sensor_msgs/msg/LaserScan', 'cdr')"
    )
    conn.execute(
        "INSERT INTO topics (id, name, type, serialization_format) "
        "VALUES (2, '/cmd_vel', 'geometry_msgs/msg/Twist', 'cdr')"
    )

    base_ns = 1713103320_000_000_000
    for i in range(3):
        ts = base_ns + i * 1_000_000_000
        conn.execute(
            "INSERT INTO messages (topic_id, timestamp, data) VALUES (1, ?, ?)",
            (ts, b"\x00" * 100),
        )
        conn.execute(
            "INSERT INTO messages (topic_id, timestamp, data) VALUES (2, ?, ?)",
            (ts + 500_000_000, b"\x00" * 50),
        )

    conn.commit()
    conn.close()


class TestParseBag:
    def test_bag_info(self, tmp_path: Path) -> None:
        bag_dir = tmp_path / "test_bag"
        _create_bag_fixture(bag_dir)
        info, messages = parse_bag(bag_dir)

        assert isinstance(info, BagInfo)
        assert info.message_count == 6
        assert len(info.topics) == 2
        assert info.duration > 0

    def test_message_count(self, tmp_path: Path) -> None:
        bag_dir = tmp_path / "test_bag"
        _create_bag_fixture(bag_dir)
        _, messages = parse_bag(bag_dir)

        assert len(messages) == 6

    def test_message_fields(self, tmp_path: Path) -> None:
        bag_dir = tmp_path / "test_bag"
        _create_bag_fixture(bag_dir)
        _, messages = parse_bag(bag_dir)

        scan_msgs = [m for m in messages if m.topic == "/scan"]
        assert len(scan_msgs) == 3
        assert all(m.message_type == "sensor_msgs/msg/LaserScan" for m in scan_msgs)
        assert all(m.size == 100 for m in scan_msgs)

    def test_timestamps_in_seconds(self, tmp_path: Path) -> None:
        bag_dir = tmp_path / "test_bag"
        _create_bag_fixture(bag_dir)
        _, messages = parse_bag(bag_dir)

        # Timestamps should be in seconds, not nanoseconds
        for m in messages:
            assert m.timestamp == pytest.approx(1713103320.0, abs=10.0)

    def test_time_range(self, tmp_path: Path) -> None:
        bag_dir = tmp_path / "test_bag"
        _create_bag_fixture(bag_dir)
        info, _ = parse_bag(bag_dir)

        start, end = info.time_range
        assert start > 0
        assert end >= start

    def test_topics_info(self, tmp_path: Path) -> None:
        bag_dir = tmp_path / "test_bag"
        _create_bag_fixture(bag_dir)
        info, _ = parse_bag(bag_dir)

        topic_names = {t["name"] for t in info.topics}
        assert topic_names == {"/scan", "/cmd_vel"}
