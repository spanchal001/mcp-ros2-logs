from __future__ import annotations

import json
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from mcp_ros2_logs.config import get_default_limit
from mcp_ros2_logs.anomaly import detect_anomalies
from mcp_ros2_logs.compare import compare_runs
from mcp_ros2_logs.correlate import correlate_logs_to_bag
from mcp_ros2_logs.query import get_node_summary, query_logs
from mcp_ros2_logs.store import LogStore
from mcp_ros2_logs.timeline import (
    MessageGroup,
    NodeGap,
    SeverityTransition,
    get_timeline,
)

mcp = FastMCP("ros2-logs")
store = LogStore()


def _ts_to_str(ts: float) -> str:
    """Convert epoch timestamp to human-readable string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _paginate(items: list, limit: int, offset: int) -> tuple[list, int, str]:
    """Slice items by offset/limit and return (page, total, truncation_notice)."""
    total = len(items)
    page = items[offset : offset + limit]
    if len(page) < total:
        notice = f"Showing {len(page)} of {total} results (offset {offset})."
        if offset + limit < total:
            notice += f" Use offset={offset + limit} to see more."
    else:
        notice = ""
    return page, total, notice


@mcp.tool()
def list_runs(
    log_dir: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> str:
    """List available ROS2 log runs with summary info.

    Args:
        log_dir: Optional path to log directory. If not provided,
                 resolves via MCP_ROS2_LOGS_DIR, ROS_LOG_DIR, or ~/.ros/log.
        limit: Maximum runs to return. Defaults to MCP_ROS2_LOGS_MAX_RESULTS (100).
        offset: Number of runs to skip (default 0).
    """
    if limit is None:
        limit = get_default_limit()
    all_summaries = store.list_runs(log_dir)
    page, _, notice = _paginate(all_summaries, limit, offset)
    output = json.dumps(
        [
            {
                "run_id": s.run_id,
                "path": str(s.path),
                "num_files": s.num_files,
                "total_lines": s.total_lines,
            }
            for s in page
        ],
        indent=2,
    )
    if notice:
        return notice + "\n\n" + output
    return output


@mcp.tool()
def load_run(run_id: str, log_dir: str | None = None) -> str:
    """Load and parse a ROS2 log run into a unified timeline.

    Args:
        run_id: The run directory name or file path.
        log_dir: Optional path to log directory.
    """
    info = store.load(run_id, log_dir)
    return json.dumps(
        {
            "run_id": info.summary.run_id,
            "nodes": info.nodes,
            "severity_counts": info.severity_counts,
            "time_range": list(info.time_range),
            "num_entries": len(info.entries),
        },
        indent=2,
    )


@mcp.tool()
def query_logs_tool(
    run_id: str,
    severity: str | None = None,
    nodes: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    text: str | None = None,
    limit: int = 50,
    offset: int = 0,
    context: int = 0,
    log_dir: str | None = None,
) -> str:
    """Search and filter the merged ROS2 log timeline. Use after load_run.

    Flexible query tool for finding specific log entries across all nodes.
    Supports filtering by severity, node, time range, and text content.
    The context parameter enables cross-node cascade analysis by including
    surrounding messages from ALL nodes around each match.

    Args:
        run_id: Run ID from list_runs or a direct path to a log file/directory.
        severity: Filter by severity level(s). Comma-separated: "ERROR",
                  "WARN,ERROR,FATAL". Case-insensitive.
        nodes: Filter by node name(s). Comma-separated: "sensor_driver",
               "planner,controller".
        time_start: Start time filter. ISO format ("2024-04-14T14:02:31"),
                    epoch ("1713103351.0"), or relative ("-30s" = 30s before
                    run end, "+10s" = 10s after run start).
        time_end: End time filter. Same format as time_start.
        text: Search message content. Plain substring by default. Interpreted
              as regex if it contains special characters (*, +, ?, [, etc).
        limit: Maximum entries to return (default 50). Total match count is
               always reported even if truncated.
        offset: Number of entries to skip (default 0).
        context: Include N messages before and after each match across ALL
                 nodes. Enables cascade analysis (e.g., context=5 shows what
                 happened on other nodes around each error). Overlapping
                 context windows are merged.
        log_dir: Optional path to log directory override.
    """
    info = store.get(run_id)
    if info is None:
        info = store.load(run_id, log_dir)

    result = query_logs(
        info.entries,
        severity=severity,
        nodes=nodes,
        time_start=time_start,
        time_end=time_end,
        text=text,
        limit=limit,
        offset=offset,
        context=context,
    )

    lines = [f"Matches: {result.total_matches}"]
    shown = len(result.matches)
    if result.truncated:
        lines.append(
            f"Showing {shown} of {result.total_matches} results (offset {offset}). "
            f"Use offset={offset + shown} to see more."
        )
    elif offset > 0:
        lines.append(f"Showing {shown} results (offset {offset}).")
    lines.append("")

    for e in result.matches:
        ts = _ts_to_str(e.timestamp)
        lines.append(f"[{e.severity}] [{ts}] [{e.node}]: {e.message}")

    return "\n".join(lines)


@mcp.tool()
def get_node_summary_tool(
    run_id: str,
    node: str,
    limit: int | None = None,
    offset: int = 0,
    log_dir: str | None = None,
) -> str:
    """Get detailed analysis of a specific node's log activity. Use after load_run.

    Provides a comprehensive summary of one node including uptime, message
    counts per severity, top recurring message patterns, all unique errors
    with timestamps, any stack traces found, and average message rate.

    Args:
        run_id: Run ID from list_runs or a direct path to a log file/directory.
        node: Node name to analyze (e.g., "sensor_driver", "motion_planner").
        limit: Cap unique_errors and stack_traces lists. Defaults to
               MCP_ROS2_LOGS_MAX_RESULTS (100).
        offset: Number of items to skip in unique_errors and stack_traces (default 0).
        log_dir: Optional path to log directory override.
    """
    info = store.get(run_id)
    if info is None:
        info = store.load(run_id, log_dir)

    summary = get_node_summary(info.entries, node)
    if summary is None:
        return f"Node '{node}' not found. Available nodes: {', '.join(info.nodes)}"

    if limit is None:
        limit = get_default_limit()
    return _format_node_summary(summary, limit=limit, offset=offset)


def _format_node_summary(
    summary: object, limit: int | None = None, offset: int = 0
) -> str:
    """Format a NodeSummary into readable text."""
    lines = [
        f"Node: {summary.node}",
        f"Uptime: {summary.uptime_seconds:.1f}s "
        f"({_ts_to_str(summary.first_message_time)} to "
        f"{_ts_to_str(summary.last_message_time)})",
        f"Total messages: {summary.total_messages}",
        f"Message rate: {summary.message_rate:.1f} msg/s",
        "",
        "Severity counts:",
    ]
    for sev, count in sorted(summary.severity_counts.items()):
        lines.append(f"  {sev}: {count}")

    lines.append("")
    lines.append("Top recurring messages:")
    for pattern, count in summary.top_recurring:
        lines.append(f"  [{count}x] {pattern}")

    if summary.unique_errors:
        errors = summary.unique_errors
        if limit is not None:
            errors, _, err_notice = _paginate(errors, limit, offset)
        else:
            err_notice = ""
        lines.append("")
        lines.append(f"Unique errors ({len(summary.unique_errors)} total):")
        if err_notice:
            lines.append(f"  {err_notice}")
        for e in errors:
            ts = _ts_to_str(e.timestamp)
            first_line = e.message.split("\n", 1)[0]
            lines.append(f"  [{e.severity}] [{ts}] {first_line}")

    if summary.stack_traces:
        traces = summary.stack_traces
        if limit is not None:
            traces, _, trace_notice = _paginate(traces, limit, offset)
        else:
            trace_notice = ""
        lines.append("")
        lines.append(f"Stack traces: {len(summary.stack_traces)} found")
        if trace_notice:
            lines.append(f"  {trace_notice}")
        for e in traces:
            ts = _ts_to_str(e.timestamp)
            lines.append(f"  [{e.severity}] [{ts}]:")
            for trace_line in e.message.split("\n"):
                lines.append(f"    {trace_line}")

    return "\n".join(lines)


def _ts_short(ts: float) -> str:
    """Short time format for timeline display."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def _format_timeline(result: object) -> str:
    """Format a TimelineResult into readable text."""
    if not result.events:
        return "No events found."

    lines: list[str] = []
    for ev in result.events:
        if isinstance(ev, MessageGroup):
            start = _ts_short(ev.time_start)
            end = _ts_short(ev.time_end)
            if ev.count == 1:
                lines.append(
                    f"[{start}] {ev.node}: {ev.severity} — {ev.sample_message}"
                )
            else:
                lines.append(
                    f"[{start} – {end}] {ev.node}: "
                    f"{ev.count} {ev.severity} — {ev.sample_message}"
                )
        elif isinstance(ev, SeverityTransition):
            ts = _ts_short(ev.timestamp)
            lines.append(f"[{ts}] {ev.node}: {ev.from_severity} -> {ev.to_severity}")
        elif isinstance(ev, NodeGap):
            start = _ts_short(ev.gap_start)
            end = _ts_short(ev.gap_end)
            lines.append(
                f"[{start} – {end}] {ev.node}: gap ({ev.gap_seconds:.1f}s, no messages)"
            )

    return "\n".join(lines)


@mcp.tool()
def get_timeline_tool(
    run_id: str,
    time_start: str | None = None,
    time_end: str | None = None,
    nodes: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    log_dir: str | None = None,
) -> str:
    """Get a condensed narrative summary of a ROS2 log run. Use after load_run.

    Compresses the full log timeline into a readable narrative by grouping
    consecutive same-severity messages, highlighting severity transitions
    (e.g., INFO -> ERROR), and flagging gaps where a node went silent.
    Essential for quickly understanding what happened in a long run.

    Args:
        run_id: Run ID from list_runs or a direct path to a log file/directory.
        time_start: Start time filter. ISO format, epoch, or relative
                    ("-30s" = 30s before run end, "+10s" = 10s after run start).
        time_end: End time filter. Same format as time_start.
        nodes: Filter by node name(s). Comma-separated: "sensor_driver,planner".
        limit: Maximum events to return. Defaults to MCP_ROS2_LOGS_MAX_RESULTS (100).
        offset: Number of events to skip (default 0).
        log_dir: Optional path to log directory override.
    """
    if limit is None:
        limit = get_default_limit()
    info = store.get(run_id)
    if info is None:
        info = store.load(run_id, log_dir)

    result = get_timeline(
        info.entries,
        time_start=time_start,
        time_end=time_end,
        nodes=nodes,
    )

    page, _, notice = _paginate(result.events, limit, offset)
    result.events = page
    output = _format_timeline(result)
    if notice:
        return notice + "\n" + output
    return output


@mcp.tool()
def compare_runs_tool(
    run_id_1: str,
    run_id_2: str,
    log_dir: str | None = None,
) -> str:
    """Compare two ROS2 log runs to find what changed. Use after loading both runs.

    Diffs a "good" run (run_id_1) against a "bad" run (run_id_2) to identify:
    new/missing nodes, severity distribution changes, novel error messages
    that only appear in run_2, the first divergence point, and timing
    differences for when errors first appeared.

    Args:
        run_id_1: First run ID (typically the "good" or baseline run).
        run_id_2: Second run ID (typically the "bad" or failing run).
        log_dir: Optional path to log directory override.
    """
    info_1 = store.get(run_id_1)
    if info_1 is None:
        info_1 = store.load(run_id_1, log_dir)
    info_2 = store.get(run_id_2)
    if info_2 is None:
        info_2 = store.load(run_id_2, log_dir)

    result = compare_runs(info_1.entries, info_2.entries)

    lines: list[str] = []

    # Node differences
    if result.nodes_only_in_1:
        lines.append(f"Nodes only in {run_id_1}: {', '.join(result.nodes_only_in_1)}")
    if result.nodes_only_in_2:
        lines.append(f"Nodes only in {run_id_2}: {', '.join(result.nodes_only_in_2)}")
    if not result.nodes_only_in_1 and not result.nodes_only_in_2:
        lines.append("Same nodes in both runs.")

    # Severity comparison
    lines.append("")
    lines.append("Severity counts per node:")
    for nc in result.common_nodes:
        lines.append(f"  {nc.node}:")
        all_sevs = sorted(set(nc.severity_counts_1) | set(nc.severity_counts_2))
        for sev in all_sevs:
            c1 = nc.severity_counts_1.get(sev, 0)
            c2 = nc.severity_counts_2.get(sev, 0)
            marker = " *" if c1 != c2 else ""
            lines.append(f"    {sev}: {c1} -> {c2}{marker}")

    # Novel messages
    if result.novel_messages:
        lines.append("")
        lines.append(
            f"Novel errors/warnings in {run_id_2} ({len(result.novel_messages)}):"
        )
        for e in result.novel_messages:
            ts = _ts_to_str(e.timestamp)
            first_line = e.message.split("\n", 1)[0]
            lines.append(f"  [{e.severity}] [{ts}] [{e.node}]: {first_line}")
    else:
        lines.append("")
        lines.append("No novel errors/warnings.")

    # First divergence
    if result.first_divergence is not None:
        lines.append("")
        lines.append(f"First divergence: {_ts_to_str(result.first_divergence)}")

    # Timing diffs
    if result.timing_diffs:
        lines.append("")
        lines.append("Timing differences:")
        for diff in result.timing_diffs:
            lines.append(f"  {diff}")

    return "\n".join(lines)


@mcp.tool()
def detect_anomalies_tool(
    run_id: str,
    baseline_ratio: float = 0.3,
    min_severity_score: float = 0.0,
    limit: int | None = None,
    offset: int = 0,
    log_dir: str | None = None,
) -> str:
    """Detect anomalous patterns in a ROS2 log run. Use after load_run.

    Statistically analyzes the run using the first portion as a baseline for
    "normal" behavior, then flags deviations: rate spikes, new error patterns,
    severity escalations, silence gaps, and error bursts.

    Args:
        run_id: Run ID from list_runs or a direct path to a log file/directory.
        baseline_ratio: Fraction of the run (by time) to use as baseline
                        (default 0.3 = first 30%).
        min_severity_score: Only return anomalies with severity_score >= this
                            value (0.0-1.0). Default 0.0 returns all.
        limit: Maximum anomalies to return. Defaults to MCP_ROS2_LOGS_MAX_RESULTS (100).
        offset: Number of anomalies to skip (default 0).
        log_dir: Optional path to log directory override.
    """
    if limit is None:
        limit = get_default_limit()
    info = store.get(run_id)
    if info is None:
        info = store.load(run_id, log_dir)

    anomalies = detect_anomalies(info.entries, baseline_ratio=baseline_ratio)

    if min_severity_score > 0:
        anomalies = [a for a in anomalies if a.severity_score >= min_severity_score]

    if not anomalies:
        return "No anomalies detected."

    page, total, notice = _paginate(anomalies, limit, offset)

    lines = [f"Anomalies detected: {total}"]
    if notice:
        lines.append(notice)
    lines.append("")
    for a in page:
        ts = _ts_to_str(a.timestamp)
        lines.append(
            f"[{a.anomaly_type}] [{ts}] [{a.node}] "
            f"(score: {a.severity_score:.2f}): {a.description}"
        )

    return "\n".join(lines)


@mcp.tool()
def list_bag_topics(
    run_id: str,
    limit: int | None = None,
    offset: int = 0,
    log_dir: str | None = None,
) -> str:
    """List topics in a ROS2 bag file with message types and counts.

    Args:
        run_id: Bag directory name or path.
        limit: Maximum topics to return. Defaults to MCP_ROS2_LOGS_MAX_RESULTS (100).
        offset: Number of topics to skip (default 0).
        log_dir: Optional path to log directory override.
    """
    if limit is None:
        limit = get_default_limit()
    bag_info, _ = store.get_bag(run_id) or store.load_bag(run_id, log_dir)

    page, _, notice = _paginate(bag_info.topics, limit, offset)

    lines = [
        f"Bag: {bag_info.path.name}",
        f"Duration: {bag_info.duration:.1f}s",
        f"Total messages: {bag_info.message_count}",
    ]
    if notice:
        lines.append(notice)
    lines.append("")
    lines.append("Topics:")
    for t in page:
        lines.append(f"  {t['name']} [{t['type']}] — {t['count']} messages")

    return "\n".join(lines)


@mcp.tool()
def query_bag_messages(
    run_id: str,
    topic: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    limit: int = 50,
    offset: int = 0,
    log_dir: str | None = None,
) -> str:
    """Query bag messages filtered by topic and time range.

    Args:
        run_id: Bag directory name or path.
        topic: Filter by topic name (e.g., "/scan", "/cmd_vel").
        time_start: Start time filter (epoch or relative "-30s").
        time_end: End time filter (epoch or relative).
        limit: Maximum messages to return (default 50).
        offset: Number of messages to skip (default 0).
        log_dir: Optional path to log directory override.
    """
    bag_info, messages = store.get_bag(run_id) or store.load_bag(run_id, log_dir)

    filtered = messages
    if topic:
        filtered = [m for m in filtered if m.topic == topic]

    if time_start:
        ts = (
            float(time_start)
            if not time_start.startswith(("-", "+"))
            else _resolve_bag_time(time_start, bag_info)
        )
        filtered = [m for m in filtered if m.timestamp >= ts]
    if time_end:
        te = (
            float(time_end)
            if not time_end.startswith(("-", "+"))
            else _resolve_bag_time(time_end, bag_info)
        )
        filtered = [m for m in filtered if m.timestamp <= te]

    total = len(filtered)
    filtered = filtered[offset : offset + limit]

    lines = [f"Messages: {total}"]
    if len(filtered) < total:
        notice = f"Showing {len(filtered)} of {total} results (offset {offset})."
        if offset + limit < total:
            notice += f" Use offset={offset + limit} to see more."
        lines.append(notice)
    lines.append("")

    for m in filtered:
        ts = _ts_to_str(m.timestamp)
        lines.append(f"[{ts}] {m.topic} [{m.message_type}] ({m.size} bytes)")

    return "\n".join(lines)


@mcp.tool()
def correlate_tool(
    run_id: str,
    bag_run_id: str | None = None,
    severity: str = "ERROR,FATAL",
    window_ms: float = 100.0,
    topics: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    log_dir: str | None = None,
) -> str:
    """Correlate log entries with bag topic messages within a time window.

    Shows what was happening on ROS2 topics around the time of log events
    (typically errors). Can correlate logs from one run with a bag from
    a different run if they share the same time window.

    Args:
        run_id: Run ID containing the log files.
        bag_run_id: Run ID containing the bag file. Defaults to run_id
                    if not provided (same run has both logs and bag).
        severity: Log severity filter (default "ERROR,FATAL").
        window_ms: Time window in milliseconds (default 100ms, symmetric).
        topics: Comma-separated topic names to include (default: all topics).
        limit: Maximum correlations to return. Defaults to
               MCP_ROS2_LOGS_MAX_RESULTS (100).
        offset: Number of correlations to skip (default 0).
        log_dir: Optional path to log directory override.
    """
    if limit is None:
        limit = get_default_limit()
    info = store.get(run_id)
    if info is None:
        info = store.load(run_id, log_dir)

    bag_id = bag_run_id or run_id
    bag_data = store.get_bag(bag_id)
    if bag_data is None:
        try:
            bag_data = store.load_bag(bag_id, log_dir)
        except FileNotFoundError:
            return f"No bag file found for run '{bag_id}'."

    _, bag_messages = bag_data
    topic_list = [t.strip() for t in topics.split(",")] if topics else None

    correlations = correlate_logs_to_bag(
        info.entries,
        bag_messages,
        window_ms=window_ms,
        topics=topic_list,
        severity=severity,
    )

    if not correlations:
        return "No correlations found."

    page, total, notice = _paginate(correlations, limit, offset)

    lines = [f"Correlations: {total}"]
    if notice:
        lines.append(notice)
    lines.append("")
    for c in page:
        ts = _ts_to_str(c.log_entry.timestamp)
        lines.append(
            f"[{c.log_entry.severity}] [{ts}] [{c.log_entry.node}]: "
            f"{c.log_entry.message.split(chr(10), 1)[0]}"
        )
        # Group nearby messages by topic
        by_topic: dict[str, list[object]] = {}
        for m in c.nearby_messages:
            by_topic.setdefault(m.topic, []).append(m)
        lines.append(f"  Nearby topics (within +/-{window_ms:.0f}ms):")
        for topic_name, msgs in sorted(by_topic.items()):
            msg_type = msgs[0].message_type
            lines.append(f"    {topic_name} ({len(msgs)} msgs, {msg_type})")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def tail_logs_tool(
    run_id: str,
    limit: int | None = None,
    offset: int = 0,
    log_dir: str | None = None,
) -> str:
    """Tail a ROS2 log run for new entries since last check.

    First call loads the run and returns a summary. Subsequent calls
    return only new entries appended since the previous call. Useful
    for monitoring an active ROS2 system.

    Args:
        run_id: Run ID from list_runs or a direct path to a log file/directory.
        limit: Maximum new entries to return. Defaults to
               MCP_ROS2_LOGS_MAX_RESULTS (100).
        offset: Number of new entries to skip (default 0).
        log_dir: Optional path to log directory override.
    """
    if limit is None:
        limit = get_default_limit()
    new_entries, is_first = store.tail(run_id, log_dir)

    if is_first:
        info = store.get(run_id)
        assert info is not None
        return (
            f"Tailing {run_id}: {len(info.entries)} existing entries, "
            f"{len(info.nodes)} nodes ({', '.join(info.nodes)}). "
            f"Call again to check for new entries."
        )

    if not new_entries:
        return "No new entries."

    page, total, notice = _paginate(new_entries, limit, offset)

    lines = [f"New entries: {total}"]
    if notice:
        lines.append(notice)
    lines.append("")
    for e in page:
        ts = _ts_to_str(e.timestamp)
        lines.append(f"[{e.severity}] [{ts}] [{e.node}]: {e.message}")

    return "\n".join(lines)


def _resolve_bag_time(time_str: str, bag_info: object) -> float:
    """Resolve relative time against bag time range."""
    start, end = bag_info.time_range
    if time_str.startswith("-"):
        return end + float(time_str[:-1] if time_str.endswith("s") else time_str)
    elif time_str.startswith("+"):
        return start + float(time_str[1:-1] if time_str.endswith("s") else time_str[1:])
    return float(time_str)


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


@mcp.resource("runs://list")
def resource_list_runs() -> str:
    """List available ROS2 log runs."""
    summaries = store.list_runs()
    return json.dumps(
        [
            {
                "run_id": s.run_id,
                "path": str(s.path),
                "num_files": s.num_files,
                "total_lines": s.total_lines,
            }
            for s in summaries
        ],
        indent=2,
    )


@mcp.resource("runs://{run_id}/summary")
def resource_run_summary(run_id: str) -> str:
    """Summary of a loaded ROS2 log run."""
    info = store.get(run_id) or store.load(run_id)
    return json.dumps(
        {
            "run_id": info.summary.run_id,
            "nodes": info.nodes,
            "severity_counts": info.severity_counts,
            "time_range": list(info.time_range),
            "num_entries": len(info.entries),
        },
        indent=2,
    )


@mcp.resource("runs://{run_id}/nodes/{node}/summary")
def resource_node_summary(run_id: str, node: str) -> str:
    """Detailed summary of a specific node's log activity."""
    info = store.get(run_id) or store.load(run_id)
    summary = get_node_summary(info.entries, node)
    if summary is None:
        return f"Node '{node}' not found. Available nodes: {', '.join(info.nodes)}"
    return _format_node_summary(summary)


@mcp.resource("runs://{run_id}/timeline")
def resource_timeline(run_id: str) -> str:
    """Condensed narrative timeline of a ROS2 log run."""
    info = store.get(run_id) or store.load(run_id)
    result = get_timeline(info.entries)
    return _format_timeline(result)


@mcp.resource("runs://{run_id}/errors")
def resource_errors(run_id: str) -> str:
    """All ERROR and FATAL log entries from a run."""
    info = store.get(run_id) or store.load(run_id)
    result = query_logs(info.entries, severity="ERROR,FATAL")
    lines = [f"Total errors: {result.total_matches}", ""]
    for e in result.matches:
        ts = _ts_to_str(e.timestamp)
        lines.append(f"[{e.severity}] [{ts}] [{e.node}]: {e.message}")
    return "\n".join(lines)


def main() -> None:
    mcp.run()
