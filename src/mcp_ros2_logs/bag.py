from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rosbags.rosbag2 import Reader


@dataclass(frozen=True, slots=True)
class BagMessage:
    timestamp: float
    topic: str
    message_type: str
    size: int


@dataclass(frozen=True, slots=True)
class BagInfo:
    path: Path
    topics: tuple[dict[str, str | int], ...]
    message_count: int
    duration: float
    time_range: tuple[float, float]


def parse_bag(bag_path: Path) -> tuple[BagInfo, list[BagMessage]]:
    """Parse a ROS2 bag directory and extract message metadata.

    Does not deserialize message payloads — only extracts timestamps,
    topic names, message types, and sizes.
    """
    messages: list[BagMessage] = []

    with Reader(bag_path) as reader:
        topics = tuple(
            {
                "name": conn.topic,
                "type": conn.msgtype,
                "count": conn.msgcount,
            }
            for conn in reader.connections
        )

        for conn, timestamp_ns, rawdata in reader.messages():
            messages.append(BagMessage(
                timestamp=timestamp_ns * 1e-9,
                topic=conn.topic,
                message_type=conn.msgtype,
                size=len(rawdata),
            ))

        start = reader.start_time * 1e-9 if reader.start_time else 0.0
        end = reader.end_time * 1e-9 if reader.end_time else 0.0
        duration = reader.duration * 1e-9 if reader.duration else 0.0
        msg_count = reader.message_count

    info = BagInfo(
        path=bag_path,
        topics=topics,
        message_count=msg_count,
        duration=duration,
        time_range=(start, end),
    )

    return info, messages
