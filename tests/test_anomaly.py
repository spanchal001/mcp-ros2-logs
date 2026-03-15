from __future__ import annotations

from mcp_ros2_logs.anomaly import detect_anomalies
from mcp_ros2_logs.parser import LogEntry


def _entry(ts: float, severity: str = "INFO", node: str = "n1", msg: str = "ok") -> LogEntry:
    return LogEntry(
        timestamp=ts,
        severity=severity,
        node=node,
        message=msg,
        source_file="test.log",
        line_number=0,
    )


class TestRateSpike:
    def test_detects_spike(self) -> None:
        # Baseline: 10 messages over 10s (1 msg/s)
        entries = [_entry(float(i)) for i in range(10)]
        # Post-baseline: 30 messages in 2s (15 msg/s)
        entries += [_entry(10.0 + i * 0.066) for i in range(30)]
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        rate_spikes = [a for a in anomalies if a.anomaly_type == "rate_spike"]
        assert len(rate_spikes) == 1
        assert rate_spikes[0].node == "n1"

    def test_no_spike_steady_rate(self) -> None:
        entries = [_entry(float(i)) for i in range(20)]
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        rate_spikes = [a for a in anomalies if a.anomaly_type == "rate_spike"]
        assert len(rate_spikes) == 0


class TestNewError:
    def test_detects_new_error(self) -> None:
        # Baseline: only INFO
        entries = [_entry(float(i)) for i in range(10)]
        # Post-baseline: a new ERROR
        entries.append(_entry(15.0, severity="ERROR", msg="Connection lost"))
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        new_errors = [a for a in anomalies if a.anomaly_type == "new_error"]
        assert len(new_errors) == 1
        assert "Connection lost" in new_errors[0].description

    def test_detects_fatal_higher_score(self) -> None:
        entries = [_entry(float(i)) for i in range(10)]
        entries.append(_entry(15.0, severity="FATAL", msg="Crash"))
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        new_errors = [a for a in anomalies if a.anomaly_type == "new_error"]
        assert len(new_errors) == 1
        assert new_errors[0].severity_score == 1.0

    def test_existing_error_not_flagged(self) -> None:
        # Same error in baseline and post
        entries = [_entry(float(i)) for i in range(10)]
        entries[5] = _entry(5.0, severity="ERROR", msg="Known issue")
        entries.append(_entry(15.0, severity="ERROR", msg="Known issue"))
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        new_errors = [a for a in anomalies if a.anomaly_type == "new_error"]
        assert len(new_errors) == 0

    def test_deduplicates_same_template(self) -> None:
        entries = [_entry(float(i)) for i in range(10)]
        entries.append(_entry(15.0, severity="ERROR", msg="Timeout after 100 ms"))
        entries.append(_entry(16.0, severity="ERROR", msg="Timeout after 200 ms"))
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        new_errors = [a for a in anomalies if a.anomaly_type == "new_error"]
        # Both normalize to "Timeout after * ms" — only one anomaly
        assert len(new_errors) == 1


class TestSeverityEscalation:
    def test_detects_escalation(self) -> None:
        entries = [_entry(float(i)) for i in range(10)]
        entries.append(_entry(15.0, severity="ERROR", msg="Something broke"))
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        escalations = [a for a in anomalies if a.anomaly_type == "severity_escalation"]
        assert len(escalations) == 1
        assert escalations[0].node == "n1"

    def test_no_escalation_if_baseline_has_errors(self) -> None:
        entries = [_entry(float(i)) for i in range(10)]
        entries[3] = _entry(3.0, severity="ERROR", msg="Baseline error")
        entries.append(_entry(15.0, severity="ERROR", msg="Post error"))
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        escalations = [a for a in anomalies if a.anomaly_type == "severity_escalation"]
        assert len(escalations) == 0

    def test_warn_escalation_lower_score(self) -> None:
        entries = [_entry(float(i)) for i in range(10)]
        entries.append(_entry(15.0, severity="WARN", msg="Warning"))
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        escalations = [a for a in anomalies if a.anomaly_type == "severity_escalation"]
        assert len(escalations) == 1
        assert escalations[0].severity_score == 0.6


class TestSilenceGap:
    def test_detects_gap(self) -> None:
        # Baseline: every 1s for 10 entries
        entries = [_entry(float(i)) for i in range(10)]
        # Post-baseline: 20s gap then resume
        entries.append(_entry(30.0))
        entries.append(_entry(31.0))
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        gaps = [a for a in anomalies if a.anomaly_type == "silence_gap"]
        assert len(gaps) == 1
        assert "Silent for" in gaps[0].description

    def test_no_gap_steady_rate(self) -> None:
        entries = [_entry(float(i)) for i in range(20)]
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        gaps = [a for a in anomalies if a.anomaly_type == "silence_gap"]
        assert len(gaps) == 0


class TestErrorBurst:
    def test_detects_burst(self) -> None:
        entries = [_entry(float(i)) for i in range(10)]
        # 5 errors in 0.5s post-baseline
        for i in range(5):
            entries.append(_entry(15.0 + i * 0.1, severity="ERROR", msg=f"err {i}"))
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        bursts = [a for a in anomalies if a.anomaly_type == "error_burst"]
        assert len(bursts) == 1
        assert "errors within" in bursts[0].description

    def test_no_burst_below_threshold(self) -> None:
        entries = [_entry(float(i)) for i in range(10)]
        # Only 2 errors (below default threshold of 3)
        entries.append(_entry(15.0, severity="ERROR", msg="err 1"))
        entries.append(_entry(15.1, severity="ERROR", msg="err 2"))
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        bursts = [a for a in anomalies if a.anomaly_type == "error_burst"]
        assert len(bursts) == 0


class TestEdgeCases:
    def test_empty_entries(self) -> None:
        assert detect_anomalies([]) == []

    def test_single_entry(self) -> None:
        assert detect_anomalies([_entry(1.0)]) == []

    def test_sorted_by_timestamp(self) -> None:
        entries = [_entry(float(i)) for i in range(10)]
        entries.append(_entry(15.0, severity="ERROR", msg="New error"))
        entries.append(_entry(30.0))  # gap
        entries.append(_entry(31.0))
        anomalies = detect_anomalies(entries, baseline_ratio=0.3)
        timestamps = [a.timestamp for a in anomalies]
        assert timestamps == sorted(timestamps)

    def test_multi_node(self) -> None:
        entries = [_entry(float(i), node="a") for i in range(10)]
        entries += [_entry(float(i), node="b") for i in range(10)]
        entries.append(_entry(15.0, severity="ERROR", node="a", msg="err"))
        entries.sort(key=lambda e: e.timestamp)
        anomalies = detect_anomalies(entries, baseline_ratio=0.5)
        # Node "a" escalated; node "b" did not
        escalations = [a for a in anomalies if a.anomaly_type == "severity_escalation"]
        assert all(a.node == "a" for a in escalations)
