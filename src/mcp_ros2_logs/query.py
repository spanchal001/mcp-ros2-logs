from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from mcp_ros2_logs.parser import LogEntry

_REGEX_SPECIAL = re.compile(r"[*+?.\[\]{}()\\|^$]")
_NUMBER_PATTERN = re.compile(r"\b\d+(\.\d+)?\b")
_RELATIVE_TIME = re.compile(r"^([+-])(\d+(?:\.\d+)?)s$")


@dataclass(slots=True)
class QueryResult:
    matches: list[LogEntry]
    total_matches: int
    truncated: bool


@dataclass(slots=True)
class NodeSummary:
    node: str
    first_message_time: float
    last_message_time: float
    uptime_seconds: float
    total_messages: int
    severity_counts: dict[str, int]
    top_recurring: list[tuple[str, int]]
    unique_errors: list[LogEntry]
    stack_traces: list[LogEntry]
    message_rate: float


def _parse_time(time_str: str, run_start: float, run_end: float) -> float:
    """Parse a time string into epoch float.

    Supports:
    - Relative: "-30s" (30s before run end), "+10s" (10s after run start)
    - Absolute epoch: "1713103320.5"
    - ISO format: "2024-04-14T14:02:00"
    """
    m = _RELATIVE_TIME.match(time_str.strip())
    if m:
        sign, seconds = m.group(1), float(m.group(2))
        if sign == "-":
            return run_end - seconds
        return run_start + seconds

    try:
        return float(time_str)
    except ValueError:
        pass

    dt = datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _make_text_matcher(text: str) -> re.Pattern[str]:
    """Create a matcher: substring if no special chars, else regex."""
    if _REGEX_SPECIAL.search(text):
        return re.compile(text)
    return re.compile(re.escape(text))


def query_logs(
    entries: list[LogEntry],
    severity: str | list[str] | None = None,
    nodes: str | list[str] | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    text: str | None = None,
    limit: int = 50,
    offset: int = 0,
    context: int = 0,
) -> QueryResult:
    """Filter the merged log timeline with optional context windows."""
    if not entries:
        return QueryResult(matches=[], total_matches=0, truncated=False)

    # Normalize filters
    sev_set: set[str] | None = None
    if severity is not None:
        if isinstance(severity, str):
            sev_set = {s.strip().upper() for s in severity.split(",")}
        else:
            sev_set = {s.strip().upper() for s in severity}

    node_set: set[str] | None = None
    if nodes is not None:
        if isinstance(nodes, str):
            node_set = {n.strip() for n in nodes.split(",")}
        else:
            node_set = {n.strip() for n in nodes}

    run_start = entries[0].timestamp
    run_end = entries[-1].timestamp

    t_start: float | None = None
    t_end: float | None = None
    if time_start is not None:
        t_start = _parse_time(time_start, run_start, run_end)
    if time_end is not None:
        t_end = _parse_time(time_end, run_start, run_end)

    text_pattern: re.Pattern[str] | None = None
    if text is not None:
        text_pattern = _make_text_matcher(text)

    # Find matching indices
    match_indices: list[int] = []
    for i, e in enumerate(entries):
        if sev_set and e.severity not in sev_set:
            continue
        if node_set and e.node not in node_set:
            continue
        if t_start is not None and e.timestamp < t_start:
            continue
        if t_end is not None and e.timestamp > t_end:
            continue
        if text_pattern and not text_pattern.search(e.message):
            continue
        match_indices.append(i)

    total_matches = len(match_indices)

    if context > 0:
        # Expand match indices with context, merge overlapping windows
        included: set[int] = set()
        for idx in match_indices:
            lo = max(0, idx - context)
            hi = min(len(entries) - 1, idx + context)
            for j in range(lo, hi + 1):
                included.add(j)
        result_indices = sorted(included)
    else:
        result_indices = match_indices

    truncated = len(result_indices) > offset + limit
    result_indices = result_indices[offset : offset + limit]

    return QueryResult(
        matches=[entries[i] for i in result_indices],
        total_matches=total_matches,
        truncated=truncated,
    )


def _normalize_message(msg: str) -> str:
    """Replace numbers/IDs with * for grouping recurring messages."""
    first_line = msg.split("\n", 1)[0]
    return _NUMBER_PATTERN.sub("*", first_line)


def get_node_summary(entries: list[LogEntry], node: str) -> NodeSummary | None:
    """Generate a detailed summary for a specific node."""
    node_entries = [e for e in entries if e.node == node]
    if not node_entries:
        return None

    first_time = node_entries[0].timestamp
    last_time = node_entries[-1].timestamp
    uptime = last_time - first_time

    severity_counts: dict[str, int] = {}
    for e in node_entries:
        severity_counts[e.severity] = severity_counts.get(e.severity, 0) + 1

    # Recurring messages (normalized)
    normalized = Counter(_normalize_message(e.message) for e in node_entries)
    top_recurring = normalized.most_common(5)

    # Unique errors
    seen_error_msgs: set[str] = set()
    unique_errors: list[LogEntry] = []
    for e in node_entries:
        if e.severity in ("ERROR", "FATAL"):
            first_line = e.message.split("\n", 1)[0]
            if first_line not in seen_error_msgs:
                seen_error_msgs.add(first_line)
                unique_errors.append(e)

    # Stack traces
    stack_traces = [e for e in node_entries if "\n" in e.message]

    # Message rate
    message_rate = len(node_entries) / uptime if uptime > 0 else 0.0

    return NodeSummary(
        node=node,
        first_message_time=first_time,
        last_message_time=last_time,
        uptime_seconds=uptime,
        total_messages=len(node_entries),
        severity_counts=severity_counts,
        top_recurring=top_recurring,
        unique_errors=unique_errors,
        stack_traces=stack_traces,
        message_rate=message_rate,
    )
