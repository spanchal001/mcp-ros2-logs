from __future__ import annotations

from dataclasses import dataclass

from mcp_ros2_logs.parser import LogEntry
from mcp_ros2_logs.query import _normalize_message


@dataclass(slots=True)
class NodeComparison:
    node: str
    severity_counts_1: dict[str, int]
    severity_counts_2: dict[str, int]


@dataclass(slots=True)
class CompareResult:
    nodes_only_in_1: list[str]
    nodes_only_in_2: list[str]
    common_nodes: list[NodeComparison]
    novel_messages: list[LogEntry]
    first_divergence: float | None
    timing_diffs: list[str]


def _severity_counts_for_node(
    entries: list[LogEntry], node: str
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in entries:
        if e.node == node:
            counts[e.severity] = counts.get(e.severity, 0) + 1
    return counts


def _first_error_offset(entries: list[LogEntry], node: str) -> float | None:
    """Return seconds from run start to first ERROR/FATAL for a node, or None."""
    if not entries:
        return None
    run_start = entries[0].timestamp
    for e in entries:
        if e.node == node and e.severity in ("ERROR", "FATAL"):
            return e.timestamp - run_start
    return None


def compare_runs(
    entries_1: list[LogEntry],
    entries_2: list[LogEntry],
) -> CompareResult:
    """Compare two runs to find what changed."""
    nodes_1 = {e.node for e in entries_1}
    nodes_2 = {e.node for e in entries_2}

    nodes_only_in_1 = sorted(nodes_1 - nodes_2)
    nodes_only_in_2 = sorted(nodes_2 - nodes_1)
    common = sorted(nodes_1 & nodes_2)

    common_nodes = [
        NodeComparison(
            node=node,
            severity_counts_1=_severity_counts_for_node(entries_1, node),
            severity_counts_2=_severity_counts_for_node(entries_2, node),
        )
        for node in common
    ]

    # Build template set from run_1 (ERROR/WARN/FATAL only)
    templates_1: set[str] = set()
    for e in entries_1:
        if e.severity in ("ERROR", "WARN", "FATAL"):
            templates_1.add(f"{e.node}::{_normalize_message(e.message)}")

    # Find novel messages in run_2
    novel: list[LogEntry] = []
    seen_novel_templates: set[str] = set()
    for e in entries_2:
        if e.severity not in ("ERROR", "WARN", "FATAL"):
            continue
        template = f"{e.node}::{_normalize_message(e.message)}"
        if template not in templates_1 and template not in seen_novel_templates:
            novel.append(e)
            seen_novel_templates.add(template)

    # First divergence
    first_divergence: float | None = None
    if novel:
        first_divergence = min(e.timestamp for e in novel)

    # Timing diffs
    timing_diffs: list[str] = []
    for node in common:
        offset_1 = _first_error_offset(entries_1, node)
        offset_2 = _first_error_offset(entries_2, node)
        if offset_2 is not None and offset_1 is None:
            timing_diffs.append(
                f"{node}: first error at T+{offset_2:.1f}s in run_2, "
                f"no errors in run_1"
            )
        elif offset_2 is not None and offset_1 is not None:
            diff = offset_2 - offset_1
            timing_diffs.append(
                f"{node}: first error at T+{offset_2:.1f}s in run_2 "
                f"vs T+{offset_1:.1f}s in run_1 (delta: {diff:+.1f}s)"
            )

    return CompareResult(
        nodes_only_in_1=nodes_only_in_1,
        nodes_only_in_2=nodes_only_in_2,
        common_nodes=common_nodes,
        novel_messages=novel,
        first_divergence=first_divergence,
        timing_diffs=timing_diffs,
    )
