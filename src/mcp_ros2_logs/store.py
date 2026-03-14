from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mcp_ros2_logs.parser import LogEntry, parse_log_file, parse_run
from mcp_ros2_logs.resolver import classify_path, resolve_log_path


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: str
    path: Path
    num_files: int
    total_lines: int


@dataclass(frozen=True, slots=True)
class RunInfo:
    summary: RunSummary
    entries: list[LogEntry]
    nodes: list[str]
    severity_counts: dict[str, int]
    time_range: tuple[float, float]


class LogStore:
    """Cache parsed runs in memory, keyed by run_id."""

    def __init__(self) -> None:
        self._cache: dict[str, RunInfo] = {}

    def list_runs(self, log_dir: str | None = None) -> list[RunSummary]:
        root = resolve_log_path(log_dir)
        kind = classify_path(root)

        if kind == "file":
            return [self._summarize_file(root)]
        elif kind == "run_dir":
            return [self._summarize_dir(root)]
        else:
            return [
                self._summarize_dir(d)
                for d in sorted(root.iterdir())
                if d.is_dir()
            ]

    def load(self, run_id: str, log_dir: str | None = None) -> RunInfo:
        if run_id in self._cache:
            return self._cache[run_id]

        root = resolve_log_path(log_dir)
        kind = classify_path(root)

        if kind == "file":
            entries = parse_log_file(root)
            run_path = root
        elif kind == "run_dir":
            entries = parse_run(root)
            run_path = root
        else:
            run_path = root / run_id
            if not run_path.exists():
                raise FileNotFoundError(f"Run not found: {run_id}")
            if run_path.is_file():
                entries = parse_log_file(run_path)
            else:
                entries = parse_run(run_path)

        info = self._build_run_info(run_id, run_path, entries)
        self._cache[run_id] = info
        return info

    def get(self, run_id: str) -> RunInfo | None:
        return self._cache.get(run_id)

    def _summarize_file(self, path: Path) -> RunSummary:
        line_count = sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
        return RunSummary(
            run_id=path.name,
            path=path,
            num_files=1,
            total_lines=line_count,
        )

    def _summarize_dir(self, path: Path) -> RunSummary:
        log_files = list(path.glob("*.log"))
        total_lines = 0
        for f in log_files:
            total_lines += sum(1 for _ in f.open(encoding="utf-8", errors="replace"))
        return RunSummary(
            run_id=path.name,
            path=path,
            num_files=len(log_files),
            total_lines=total_lines,
        )

    def _build_run_info(
        self, run_id: str, run_path: Path, entries: list[LogEntry]
    ) -> RunInfo:
        nodes = sorted({e.node for e in entries})
        severity_counts: dict[str, int] = {}
        for e in entries:
            severity_counts[e.severity] = severity_counts.get(e.severity, 0) + 1

        if entries:
            time_range = (entries[0].timestamp, entries[-1].timestamp)
        else:
            time_range = (0.0, 0.0)

        log_files = list(run_path.glob("*.log")) if run_path.is_dir() else [run_path]
        total_lines = 0
        for f in log_files:
            total_lines += sum(1 for _ in f.open(encoding="utf-8", errors="replace"))

        summary = RunSummary(
            run_id=run_id,
            path=run_path,
            num_files=len(log_files),
            total_lines=total_lines,
        )

        return RunInfo(
            summary=summary,
            entries=entries,
            nodes=nodes,
            severity_counts=severity_counts,
            time_range=time_range,
        )
