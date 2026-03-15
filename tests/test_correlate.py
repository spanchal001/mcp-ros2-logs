from __future__ import annotations

from mcp_ros2_logs.bag import BagMessage
from mcp_ros2_logs.correlate import correlate_logs_to_bag
from mcp_ros2_logs.parser import LogEntry


def _entry(ts: float, severity: str = "ERROR", node: str = "n1", msg: str = "err") -> LogEntry:
    return LogEntry(
        timestamp=ts, severity=severity, node=node, message=msg,
        source_file="test.log", line_number=0,
    )


def _bag_msg(ts: float, topic: str = "/scan", msg_type: str = "sensor_msgs/msg/LaserScan") -> BagMessage:
    return BagMessage(timestamp=ts, topic=topic, message_type=msg_type, size=100)


class TestCorrelation:
    def test_finds_nearby_messages(self) -> None:
        entries = [_entry(10.0)]
        bag = [_bag_msg(9.95), _bag_msg(10.02), _bag_msg(10.5)]
        result = correlate_logs_to_bag(entries, bag, window_ms=100)
        assert len(result) == 1
        assert len(result[0].nearby_messages) == 2  # 9.95 and 10.02

    def test_no_match_outside_window(self) -> None:
        entries = [_entry(10.0)]
        bag = [_bag_msg(10.5), _bag_msg(11.0)]
        result = correlate_logs_to_bag(entries, bag, window_ms=100)
        assert len(result) == 0

    def test_severity_filter(self) -> None:
        entries = [_entry(10.0, severity="INFO"), _entry(11.0, severity="ERROR")]
        bag = [_bag_msg(10.0), _bag_msg(11.0)]
        result = correlate_logs_to_bag(entries, bag, window_ms=100, severity="ERROR")
        assert len(result) == 1
        assert result[0].log_entry.severity == "ERROR"

    def test_topic_filter(self) -> None:
        entries = [_entry(10.0)]
        bag = [
            _bag_msg(10.0, topic="/scan"),
            _bag_msg(10.0, topic="/cmd_vel", msg_type="geometry_msgs/msg/Twist"),
        ]
        result = correlate_logs_to_bag(entries, bag, window_ms=100, topics=["/scan"])
        assert len(result) == 1
        assert all(m.topic == "/scan" for m in result[0].nearby_messages)

    def test_multiple_entries(self) -> None:
        entries = [_entry(10.0), _entry(20.0)]
        bag = [_bag_msg(10.0), _bag_msg(20.0)]
        result = correlate_logs_to_bag(entries, bag, window_ms=100)
        assert len(result) == 2

    def test_empty_inputs(self) -> None:
        assert correlate_logs_to_bag([], [], window_ms=100) == []
        assert correlate_logs_to_bag([_entry(10.0)], [], window_ms=100) == []
        assert correlate_logs_to_bag([], [_bag_msg(10.0)], window_ms=100) == []

    def test_window_ms_in_result(self) -> None:
        entries = [_entry(10.0)]
        bag = [_bag_msg(10.0)]
        result = correlate_logs_to_bag(entries, bag, window_ms=200)
        assert result[0].window_ms == 200.0

    def test_large_window(self) -> None:
        entries = [_entry(10.0)]
        bag = [_bag_msg(9.0), _bag_msg(10.0), _bag_msg(11.0)]
        result = correlate_logs_to_bag(entries, bag, window_ms=1500)
        assert len(result) == 1
        assert len(result[0].nearby_messages) == 3
