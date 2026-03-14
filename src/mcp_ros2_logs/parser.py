from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path

_LOG_PATTERN = re.compile(
    r"^\[(DEBUG|INFO|WARN|ERROR|FATAL)\]\s+\[(\d+\.\d+)\]\s+\[([^\]]+)\]:\s*(.*)"
)


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: float
    severity: str
    node: str
    message: str
    source_file: str
    line_number: int


def parse_log_file(path: Path) -> list[LogEntry]:
    """Parse a single ROS2 spdlog file into a list of LogEntry objects."""
    entries: list[LogEntry] = []
    current: LogEntry | None = None

    text = path.read_text(encoding="utf-8", errors="replace")

    for line_number, raw_line in enumerate(text.splitlines(), 1):
        match = _LOG_PATTERN.match(raw_line)
        if match:
            if current is not None:
                entries.append(current)
            current = LogEntry(
                timestamp=float(match.group(2)),
                severity=match.group(1),
                node=match.group(3),
                message=match.group(4),
                source_file=path.name,
                line_number=line_number,
            )
        elif current is not None:
            current = dataclasses.replace(
                current,
                message=current.message + "\n" + raw_line.rstrip(),
            )
        # Lines before first valid entry are silently skipped

    if current is not None:
        entries.append(current)

    return entries


def parse_run(run_path: Path) -> list[LogEntry]:
    """Parse all .log files in a run directory, merge and sort by timestamp."""
    entries: list[LogEntry] = []
    for log_file in sorted(run_path.glob("*.log")):
        entries.extend(parse_log_file(log_file))
    entries.sort(key=lambda e: (e.timestamp, e.line_number))
    return entries
