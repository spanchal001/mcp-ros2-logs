from __future__ import annotations

import dataclasses
import os
import re
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_FORMAT = "[{severity}] [{time}] [{name}]: {message}"

_PLACEHOLDER_PATTERNS: dict[str, str] = {
    "severity": r"(DEBUG|INFO|WARN|ERROR|FATAL)",
    "time": r"(\d+\.\d+)",
    "name": r"([^\s\]\):]+)",
    "function_name": r"([^\s\]\):]+)",
    "file_name": r"([^\s\]\):]+)",
    "line_number": r"(\d+)",
}

_PLACEHOLDER_RE = re.compile(r"\\\{(\w+)\\\}")


@dataclass(frozen=True, slots=True)
class LogFormat:
    pattern: re.Pattern[str]
    field_order: list[str]


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: float
    severity: str
    node: str
    message: str
    source_file: str
    line_number: int
    function_name: str | None = None
    source_code_file: str | None = None
    source_code_line: int | None = None


def compile_format(fmt: str) -> LogFormat:
    """Convert an RCUTILS_CONSOLE_OUTPUT_FORMAT string into a compiled LogFormat."""
    escaped = re.escape(fmt)
    field_order: list[str] = []

    # Find all escaped placeholders and determine which is last
    placeholders = list(_PLACEHOLDER_RE.finditer(escaped))
    last_placeholder_name = placeholders[-1].group(1) if placeholders else None

    def _replace(m: re.Match[str]) -> str:
        name = m.group(1)
        field_order.append(name)
        if name == "message":
            return "(.*)" if name == last_placeholder_name else "(.*?)"
        if name in _PLACEHOLDER_PATTERNS:
            return _PLACEHOLDER_PATTERNS[name]
        # Unknown placeholder — capture as non-whitespace
        return r"(\S+)"

    regex_str = _PLACEHOLDER_RE.sub(_replace, escaped)
    return LogFormat(
        pattern=re.compile("^" + regex_str),
        field_order=field_order,
    )


def get_log_format() -> LogFormat:
    """Build a LogFormat from RCUTILS_CONSOLE_OUTPUT_FORMAT or the default."""
    fmt_str = os.environ.get("RCUTILS_CONSOLE_OUTPUT_FORMAT", _DEFAULT_FORMAT)
    return compile_format(fmt_str)


def _node_from_filename(filename: str) -> str:
    """Extract node name from ROS2 log filename like 'talker_12345_20240414-140200.log'."""
    stem = Path(filename).stem
    if not stem or stem.startswith("."):
        return "unknown"
    parts = stem.split("_")
    # Drop trailing PID (all digits) and timestamp (YYYYMMDD-HHMMSS) segments
    while len(parts) > 1 and (
        parts[-1].isdigit()
        or re.match(r"\d{8}", parts[-1].split("-")[0])
    ):
        parts.pop()
    return "_".join(parts) if parts else "unknown"


def _entry_from_match(
    match: re.Match[str],
    fmt: LogFormat,
    source_file: str,
    file_line_number: int,
    fallback_node: str,
) -> LogEntry:
    """Build a LogEntry from a regex match using the format's field order."""
    fields: dict[str, str] = {}
    for i, name in enumerate(fmt.field_order):
        fields[name] = match.group(i + 1)

    return LogEntry(
        timestamp=float(fields["time"]) if "time" in fields else 0.0,
        severity=fields.get("severity", "INFO"),
        node=fields.get("name", fallback_node),
        message=fields.get("message", ""),
        source_file=source_file,
        line_number=file_line_number,
        function_name=fields.get("function_name"),
        source_code_file=fields.get("file_name"),
        source_code_line=int(fields["line_number"]) if "line_number" in fields else None,
    )


def parse_log_file(path: Path, fmt: LogFormat | None = None) -> list[LogEntry]:
    """Parse a single ROS2 spdlog file into a list of LogEntry objects."""
    if fmt is None:
        fmt = get_log_format()

    entries: list[LogEntry] = []
    current: LogEntry | None = None
    fallback_node = _node_from_filename(path.name)

    text = path.read_text(encoding="utf-8", errors="replace")

    for line_number, raw_line in enumerate(text.splitlines(), 1):
        match = fmt.pattern.match(raw_line)
        if match:
            if current is not None:
                entries.append(current)
            current = _entry_from_match(
                match, fmt, path.name, line_number, fallback_node
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


def parse_run(run_path: Path, fmt: LogFormat | None = None) -> list[LogEntry]:
    """Parse all .log files in a run directory, merge and sort by timestamp."""
    if fmt is None:
        fmt = get_log_format()
    entries: list[LogEntry] = []
    for log_file in sorted(run_path.glob("*.log")):
        entries.extend(parse_log_file(log_file, fmt))
    entries.sort(key=lambda e: (e.timestamp, e.line_number))
    return entries
