from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mcp_ros2_logs.parser import LogFormat, get_log_format, parse_log_file


@dataclass
class TailState:
    run_id: str
    file_positions: dict[str, int] = field(default_factory=dict)
    last_entry_counts: dict[str, int] = field(default_factory=dict)


class TailWatcher:
    """Track file positions for incremental log reading."""

    def __init__(self) -> None:
        self._states: dict[str, TailState] = {}

    def initialize(self, run_id: str, run_path: Path) -> None:
        """Record current EOF positions for all log files in a run."""
        state = TailState(run_id=run_id)
        if run_path.is_dir():
            for log_file in sorted(run_path.glob("*.log")):
                state.file_positions[log_file.name] = log_file.stat().st_size
                entries = parse_log_file(log_file)
                state.last_entry_counts[log_file.name] = len(entries)
        elif run_path.is_file():
            state.file_positions[run_path.name] = run_path.stat().st_size
            entries = parse_log_file(run_path)
            state.last_entry_counts[run_path.name] = len(entries)
        self._states[run_id] = state

    def check_updates(
        self,
        run_path: Path,
        run_id: str,
        fmt: LogFormat | None = None,
    ) -> list:
        """Read new entries from log files since last check."""
        from mcp_ros2_logs.parser import LogEntry

        if fmt is None:
            fmt = get_log_format()

        state = self._states.get(run_id)
        if state is None:
            return []

        new_entries: list[LogEntry] = []

        if run_path.is_dir():
            log_files = sorted(run_path.glob("*.log"))
        elif run_path.is_file():
            log_files = [run_path]
        else:
            return []

        for log_file in log_files:
            name = log_file.name
            current_size = log_file.stat().st_size
            last_size = state.file_positions.get(name, 0)

            if current_size <= last_size:
                # Check for new files not previously tracked
                if name not in state.file_positions:
                    entries = parse_log_file(log_file, fmt=fmt)
                    new_entries.extend(entries)
                    state.file_positions[name] = current_size
                    state.last_entry_counts[name] = len(entries)
                continue

            # File has grown — re-parse and return entries after last known count
            entries = parse_log_file(log_file, fmt=fmt)
            last_count = state.last_entry_counts.get(name, 0)
            if len(entries) > last_count:
                new_entries.extend(entries[last_count:])

            state.file_positions[name] = current_size
            state.last_entry_counts[name] = len(entries)

        new_entries.sort(key=lambda e: (e.timestamp, e.line_number))
        return new_entries

    def has_state(self, run_id: str) -> bool:
        return run_id in self._states
