from __future__ import annotations

import json
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from mcp_ros2_logs.compare import compare_runs
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


@mcp.tool()
def list_runs(log_dir: str | None = None) -> str:
    """List available ROS2 log runs with summary info.

    Args:
        log_dir: Optional path to log directory. If not provided,
                 resolves via MCP_ROS2_LOGS_DIR, ROS_LOG_DIR, or ~/.ros/log.
    """
    summaries = store.list_runs(log_dir)
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
        context=context,
    )

    lines = [f"Matches: {result.total_matches}"]
    if result.truncated:
        lines[0] += f" (showing first {len(result.matches)})"
    lines.append("")

    for e in result.matches:
        ts = _ts_to_str(e.timestamp)
        lines.append(f"[{e.severity}] [{ts}] [{e.node}]: {e.message}")

    return "\n".join(lines)


@mcp.tool()
def get_node_summary_tool(
    run_id: str,
    node: str,
    log_dir: str | None = None,
) -> str:
    """Get detailed analysis of a specific node's log activity. Use after load_run.

    Provides a comprehensive summary of one node including uptime, message
    counts per severity, top recurring message patterns, all unique errors
    with timestamps, any stack traces found, and average message rate.

    Args:
        run_id: Run ID from list_runs or a direct path to a log file/directory.
        node: Node name to analyze (e.g., "sensor_driver", "motion_planner").
        log_dir: Optional path to log directory override.
    """
    info = store.get(run_id)
    if info is None:
        info = store.load(run_id, log_dir)

    summary = get_node_summary(info.entries, node)
    if summary is None:
        return f"Node '{node}' not found. Available nodes: {', '.join(info.nodes)}"

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
        lines.append("")
        lines.append("Unique errors:")
        for e in summary.unique_errors:
            ts = _ts_to_str(e.timestamp)
            first_line = e.message.split("\n", 1)[0]
            lines.append(f"  [{e.severity}] [{ts}] {first_line}")

    if summary.stack_traces:
        lines.append("")
        lines.append(f"Stack traces: {len(summary.stack_traces)} found")
        for e in summary.stack_traces:
            ts = _ts_to_str(e.timestamp)
            lines.append(f"  [{e.severity}] [{ts}]:")
            for trace_line in e.message.split("\n"):
                lines.append(f"    {trace_line}")

    return "\n".join(lines)


def _ts_short(ts: float) -> str:
    """Short time format for timeline display."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]


@mcp.tool()
def get_timeline_tool(
    run_id: str,
    time_start: str | None = None,
    time_end: str | None = None,
    nodes: str | None = None,
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
        log_dir: Optional path to log directory override.
    """
    info = store.get(run_id)
    if info is None:
        info = store.load(run_id, log_dir)

    result = get_timeline(
        info.entries,
        time_start=time_start,
        time_end=time_end,
        nodes=nodes,
    )

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
            lines.append(
                f"[{ts}] {ev.node}: {ev.from_severity} -> {ev.to_severity}"
            )
        elif isinstance(ev, NodeGap):
            start = _ts_short(ev.gap_start)
            end = _ts_short(ev.gap_end)
            lines.append(
                f"[{start} – {end}] {ev.node}: gap ({ev.gap_seconds:.1f}s, no messages)"
            )

    return "\n".join(lines)


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
        lines.append(f"Novel errors/warnings in {run_id_2} ({len(result.novel_messages)}):")
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
        lines.append(
            f"First divergence: {_ts_to_str(result.first_divergence)}"
        )

    # Timing diffs
    if result.timing_diffs:
        lines.append("")
        lines.append("Timing differences:")
        for diff in result.timing_diffs:
            lines.append(f"  {diff}")

    return "\n".join(lines)


def main() -> None:
    mcp.run()
