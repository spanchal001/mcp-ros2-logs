from __future__ import annotations

import bisect
from dataclasses import dataclass

from mcp_ros2_logs.bag import BagMessage
from mcp_ros2_logs.parser import LogEntry


@dataclass(frozen=True, slots=True)
class Correlation:
    log_entry: LogEntry
    nearby_messages: tuple[BagMessage, ...]
    window_ms: float


def correlate_logs_to_bag(
    entries: list[LogEntry],
    bag_messages: list[BagMessage],
    window_ms: float = 100.0,
    topics: list[str] | None = None,
    severity: str | None = None,
) -> list[Correlation]:
    """Find bag messages within a time window around each log entry.

    Args:
        entries: Log entries to correlate (typically filtered by severity).
        bag_messages: Bag messages sorted by timestamp.
        window_ms: Time window in milliseconds (symmetric, +/-).
        topics: Optional list of topic names to include.
        severity: Comma-separated severity filter (e.g., "ERROR,FATAL").
    """
    if not entries or not bag_messages:
        return []

    # Filter log entries by severity
    if severity:
        sev_set = {s.strip().upper() for s in severity.split(",")}
        entries = [e for e in entries if e.severity in sev_set]

    # Filter bag messages by topic
    filtered_msgs = bag_messages
    if topics:
        topic_set = set(topics)
        filtered_msgs = [m for m in bag_messages if m.topic in topic_set]

    if not entries or not filtered_msgs:
        return []

    # Build timestamp array for binary search
    msg_timestamps = [m.timestamp for m in filtered_msgs]
    window_s = window_ms / 1000.0

    correlations: list[Correlation] = []
    for entry in entries:
        lo = bisect.bisect_left(msg_timestamps, entry.timestamp - window_s)
        hi = bisect.bisect_right(msg_timestamps, entry.timestamp + window_s)
        if lo < hi:
            nearby = tuple(filtered_msgs[lo:hi])
            correlations.append(Correlation(
                log_entry=entry,
                nearby_messages=nearby,
                window_ms=window_ms,
            ))

    return correlations
