from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from mcp_ros2_logs.parser import LogEntry
from mcp_ros2_logs.query import _normalize_message

_ERROR_SEVERITIES = {"ERROR", "FATAL"}
_ESCALATION_SEVERITIES = {"WARN", "ERROR", "FATAL"}
_BENIGN_SEVERITIES = {"DEBUG", "INFO"}


@dataclass(slots=True)
class Anomaly:
    anomaly_type: str
    timestamp: float
    node: str
    description: str
    severity_score: float
    related_entries: list[LogEntry] = field(default_factory=list)


def detect_anomalies(
    entries: list[LogEntry],
    baseline_ratio: float = 0.3,
    rate_window_s: float = 5.0,
    rate_spike_factor: float = 3.0,
    burst_window_s: float = 1.0,
    burst_threshold: int = 3,
) -> list[Anomaly]:
    """Detect anomalous patterns in a log run.

    Uses the first `baseline_ratio` fraction of entries (by timestamp) as
    the definition of "normal" behavior, then scans the remainder for
    deviations.
    """
    if len(entries) < 2:
        return []

    t_start = entries[0].timestamp
    t_end = entries[-1].timestamp
    duration = t_end - t_start
    if duration <= 0:
        return []

    t_baseline_end = t_start + duration * baseline_ratio
    baseline = [e for e in entries if e.timestamp <= t_baseline_end]
    post_baseline = [e for e in entries if e.timestamp > t_baseline_end]

    if not baseline or not post_baseline:
        return []

    anomalies: list[Anomaly] = []
    anomalies.extend(_detect_rate_spikes(baseline, post_baseline, rate_window_s, rate_spike_factor))
    anomalies.extend(_detect_new_errors(baseline, post_baseline))
    anomalies.extend(_detect_severity_escalation(baseline, post_baseline))
    anomalies.extend(_detect_silence_gaps(baseline, post_baseline))
    anomalies.extend(_detect_error_bursts(post_baseline, burst_window_s, burst_threshold))

    anomalies.sort(key=lambda a: a.timestamp)
    return anomalies


def _entries_by_node(entries: list[LogEntry]) -> dict[str, list[LogEntry]]:
    by_node: dict[str, list[LogEntry]] = defaultdict(list)
    for e in entries:
        by_node[e.node].append(e)
    return dict(by_node)


def _detect_rate_spikes(
    baseline: list[LogEntry],
    post: list[LogEntry],
    window_s: float,
    spike_factor: float,
) -> list[Anomaly]:
    """Flag nodes whose message rate exceeds spike_factor * baseline mean."""
    baseline_by_node = _entries_by_node(baseline)
    post_by_node = _entries_by_node(post)
    anomalies: list[Anomaly] = []

    for node, node_baseline in baseline_by_node.items():
        if len(node_baseline) < 2:
            continue
        bl_duration = node_baseline[-1].timestamp - node_baseline[0].timestamp
        if bl_duration <= 0:
            continue
        baseline_rate = len(node_baseline) / bl_duration

        node_post = post_by_node.get(node, [])
        if len(node_post) < 2:
            continue

        # Sliding window over post-baseline entries
        window_start_idx = 0
        for i, entry in enumerate(node_post):
            while node_post[window_start_idx].timestamp < entry.timestamp - window_s:
                window_start_idx += 1
            window_count = i - window_start_idx + 1
            window_duration = entry.timestamp - node_post[window_start_idx].timestamp
            if window_duration > 0:
                window_rate = window_count / window_duration
                if window_rate > spike_factor * baseline_rate:
                    score = min(1.0, window_rate / (spike_factor * baseline_rate) - 1.0)
                    window_entries = node_post[window_start_idx : i + 1]
                    anomalies.append(Anomaly(
                        anomaly_type="rate_spike",
                        timestamp=entry.timestamp,
                        node=node,
                        description=(
                            f"Message rate {window_rate:.1f}/s exceeds "
                            f"{spike_factor:.0f}x baseline ({baseline_rate:.1f}/s)"
                        ),
                        severity_score=score,
                        related_entries=window_entries,
                    ))
                    break  # One anomaly per node

    return anomalies


def _detect_new_errors(
    baseline: list[LogEntry],
    post: list[LogEntry],
) -> list[Anomaly]:
    """Flag ERROR/FATAL messages with templates not seen in baseline."""
    baseline_templates: set[str] = set()
    for e in baseline:
        if e.severity in _ERROR_SEVERITIES:
            baseline_templates.add(f"{e.node}::{_normalize_message(e.message)}")

    anomalies: list[Anomaly] = []
    seen_post: set[str] = set()

    for e in post:
        if e.severity not in _ERROR_SEVERITIES:
            continue
        template = f"{e.node}::{_normalize_message(e.message)}"
        if template not in baseline_templates and template not in seen_post:
            seen_post.add(template)
            score = 1.0 if e.severity == "FATAL" else 0.8
            anomalies.append(Anomaly(
                anomaly_type="new_error",
                timestamp=e.timestamp,
                node=e.node,
                description=f"New {e.severity}: {e.message.split(chr(10), 1)[0]}",
                severity_score=score,
                related_entries=[e],
            ))

    return anomalies


def _detect_severity_escalation(
    baseline: list[LogEntry],
    post: list[LogEntry],
) -> list[Anomaly]:
    """Flag nodes that escalate from benign-only to WARN/ERROR/FATAL."""
    baseline_by_node = _entries_by_node(baseline)
    anomalies: list[Anomaly] = []

    benign_nodes: set[str] = set()
    for node, node_entries in baseline_by_node.items():
        severities = {e.severity for e in node_entries}
        if severities <= _BENIGN_SEVERITIES:
            benign_nodes.add(node)

    escalated: set[str] = set()
    for e in post:
        if e.node in benign_nodes and e.severity in _ESCALATION_SEVERITIES and e.node not in escalated:
            escalated.add(e.node)
            score = 0.9 if e.severity in _ERROR_SEVERITIES else 0.6
            anomalies.append(Anomaly(
                anomaly_type="severity_escalation",
                timestamp=e.timestamp,
                node=e.node,
                description=(
                    f"Node escalated from INFO/DEBUG to {e.severity}"
                ),
                severity_score=score,
                related_entries=[e],
            ))

    return anomalies


def _detect_silence_gaps(
    baseline: list[LogEntry],
    post: list[LogEntry],
) -> list[Anomaly]:
    """Flag nodes that go silent for >2x their baseline average interval."""
    baseline_by_node = _entries_by_node(baseline)
    post_by_node = _entries_by_node(post)
    anomalies: list[Anomaly] = []

    for node, node_baseline in baseline_by_node.items():
        if len(node_baseline) < 3:
            continue
        intervals = [
            node_baseline[i].timestamp - node_baseline[i - 1].timestamp
            for i in range(1, len(node_baseline))
        ]
        avg_interval = sum(intervals) / len(intervals)
        if avg_interval <= 0:
            continue
        threshold = max(5.0, 2.0 * avg_interval)

        node_post = post_by_node.get(node, [])
        # Check gap between last baseline entry and first post entry
        all_entries = [node_baseline[-1]] + node_post
        for i in range(1, len(all_entries)):
            gap = all_entries[i].timestamp - all_entries[i - 1].timestamp
            if gap > threshold:
                score = min(1.0, gap / (4.0 * avg_interval))
                anomalies.append(Anomaly(
                    anomaly_type="silence_gap",
                    timestamp=all_entries[i - 1].timestamp,
                    node=node,
                    description=(
                        f"Silent for {gap:.1f}s (baseline interval: {avg_interval:.1f}s)"
                    ),
                    severity_score=score,
                ))
                break  # One gap anomaly per node

    return anomalies


def _detect_error_bursts(
    post: list[LogEntry],
    window_s: float,
    threshold: int,
) -> list[Anomaly]:
    """Flag bursts of >=threshold ERROR/FATAL entries within window_s."""
    errors_by_node: dict[str, list[LogEntry]] = defaultdict(list)
    for e in post:
        if e.severity in _ERROR_SEVERITIES:
            errors_by_node[e.node].append(e)

    anomalies: list[Anomaly] = []
    for node, errors in errors_by_node.items():
        if len(errors) < threshold:
            continue
        start_idx = 0
        for i, entry in enumerate(errors):
            while errors[start_idx].timestamp < entry.timestamp - window_s:
                start_idx += 1
            count = i - start_idx + 1
            if count >= threshold:
                burst_entries = errors[start_idx : i + 1]
                score = min(1.0, count / (2.0 * threshold))
                anomalies.append(Anomaly(
                    anomaly_type="error_burst",
                    timestamp=errors[start_idx].timestamp,
                    node=node,
                    description=f"{count} errors within {window_s:.1f}s",
                    severity_score=score,
                    related_entries=burst_entries,
                ))
                break  # One burst anomaly per node

    return anomalies
