from __future__ import annotations

from dataclasses import dataclass

from mcp_ros2_logs.parser import LogEntry
from mcp_ros2_logs.query import _parse_time


@dataclass(slots=True)
class MessageGroup:
    node: str
    severity: str
    count: int
    time_start: float
    time_end: float
    sample_message: str


@dataclass(slots=True)
class SeverityTransition:
    timestamp: float
    node: str
    from_severity: str
    to_severity: str


@dataclass(slots=True)
class NodeGap:
    node: str
    gap_start: float
    gap_end: float
    gap_seconds: float


@dataclass(slots=True)
class TimelineResult:
    events: list[MessageGroup | SeverityTransition | NodeGap]


def _truncate(text: str, max_len: int = 80) -> str:
    first_line = text.split("\n", 1)[0]
    if len(first_line) <= max_len:
        return first_line
    return first_line[: max_len - 3] + "..."


def _compute_gap_thresholds(
    entries: list[LogEntry],
) -> dict[str, float]:
    """Compute per-node gap threshold as 2x average interval from first 10 messages."""
    node_timestamps: dict[str, list[float]] = {}
    for e in entries:
        ts_list = node_timestamps.setdefault(e.node, [])
        if len(ts_list) < 11:
            ts_list.append(e.timestamp)

    thresholds: dict[str, float] = {}
    for node, timestamps in node_timestamps.items():
        if len(timestamps) < 2:
            thresholds[node] = 5.0
            continue
        intervals = [
            timestamps[i] - timestamps[i - 1]
            for i in range(1, min(len(timestamps), 11))
        ]
        avg = sum(intervals) / len(intervals)
        thresholds[node] = max(avg * 2.0, 5.0)

    return thresholds


def get_timeline(
    entries: list[LogEntry],
    time_start: str | None = None,
    time_end: str | None = None,
    nodes: str | list[str] | None = None,
) -> TimelineResult:
    """Build a condensed narrative timeline from log entries."""
    if not entries:
        return TimelineResult(events=[])

    run_start = entries[0].timestamp
    run_end = entries[-1].timestamp

    # Filter by time
    t_start: float | None = None
    t_end: float | None = None
    if time_start is not None:
        t_start = _parse_time(time_start, run_start, run_end)
    if time_end is not None:
        t_end = _parse_time(time_end, run_start, run_end)

    # Filter by nodes
    node_set: set[str] | None = None
    if nodes is not None:
        if isinstance(nodes, str):
            node_set = {n.strip() for n in nodes.split(",")}
        else:
            node_set = {n.strip() for n in nodes}

    filtered: list[LogEntry] = []
    for e in entries:
        if t_start is not None and e.timestamp < t_start:
            continue
        if t_end is not None and e.timestamp > t_end:
            continue
        if node_set is not None and e.node not in node_set:
            continue
        filtered.append(e)

    if not filtered:
        return TimelineResult(events=[])

    gap_thresholds = _compute_gap_thresholds(filtered)

    # Track per-node state
    node_last_severity: dict[str, str] = {}
    node_last_timestamp: dict[str, float] = {}
    # Current open group per node
    open_groups: dict[str, MessageGroup] = {}

    events: list[MessageGroup | SeverityTransition | NodeGap] = []

    for e in filtered:
        node = e.node

        # Check for gap
        if node in node_last_timestamp:
            gap = e.timestamp - node_last_timestamp[node]
            threshold = gap_thresholds.get(node, 5.0)
            if gap > threshold:
                # Close current group if open
                if node in open_groups:
                    events.append(open_groups.pop(node))
                events.append(
                    NodeGap(
                        node=node,
                        gap_start=node_last_timestamp[node],
                        gap_end=e.timestamp,
                        gap_seconds=gap,
                    )
                )

        # Check for severity transition
        if node in node_last_severity and node_last_severity[node] != e.severity:
            # Close current group
            if node in open_groups:
                events.append(open_groups.pop(node))
            events.append(
                SeverityTransition(
                    timestamp=e.timestamp,
                    node=node,
                    from_severity=node_last_severity[node],
                    to_severity=e.severity,
                )
            )

        # Add to current group or start new one
        if node in open_groups and open_groups[node].severity == e.severity:
            grp = open_groups[node]
            grp.count += 1
            grp.time_end = e.timestamp
        else:
            if node in open_groups:
                events.append(open_groups.pop(node))
            open_groups[node] = MessageGroup(
                node=node,
                severity=e.severity,
                count=1,
                time_start=e.timestamp,
                time_end=e.timestamp,
                sample_message=_truncate(e.message),
            )

        node_last_severity[node] = e.severity
        node_last_timestamp[node] = e.timestamp

    # Close remaining open groups
    for grp in open_groups.values():
        events.append(grp)

    # Sort by start time
    def _event_time(ev: MessageGroup | SeverityTransition | NodeGap) -> float:
        if isinstance(ev, MessageGroup):
            return ev.time_start
        if isinstance(ev, SeverityTransition):
            return ev.timestamp
        return ev.gap_start

    events.sort(key=_event_time)

    return TimelineResult(events=events)
