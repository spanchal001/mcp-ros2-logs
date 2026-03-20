# Changelog

All notable changes to mcp-ros2-logs are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.4.0] - 2026-03-19

### Added
- **Pagination**: `limit` and `offset` parameters on all list-returning tools (`list_runs`, `query_logs`, `get_node_summary`, `get_timeline`, `detect_anomalies`, `list_bag_topics`, `query_bag_messages`, `correlate`, `tail_logs`). Truncated output includes a notice with the next offset value.
- `MCP_ROS2_LOGS_MAX_RESULTS` environment variable to set the default result limit globally (default: 100).
- `config.py` module for runtime configuration.
- `CHANGELOG.md` for tracking release notes.
- Pagination test suite (`test_pagination.py`, 11 tests).
- 182 tests (up from 171).

### Changed
- `correlate`: `nearby_messages` per correlation capped at 20 to prevent unbounded output on wide time windows.
- `query_logs` and `query_bag_messages` now accept an `offset` parameter (existing `limit` default of 50 unchanged).

## [0.3.0] - 2026-03-15

### Added
- `detect_anomalies` tool: statistically flags rate spikes, new error patterns, severity escalations, silence gaps, and error bursts using the first portion of a run as baseline.
- `list_bag_topics` and `query_bag_messages` tools: parse .db3/.mcap bag files without ROS2 installed. Extracts topic metadata without deserializing message payloads.
- `correlate` tool: cross-reference log errors with bag topic messages within a configurable time window. Supports correlating across different runs via `bag_run_id`.
- `tail_logs` tool: polling-based incremental log reading for monitoring active ROS2 systems.
- 5 MCP resources: `runs://list`, `runs://{run_id}/summary`, `runs://{run_id}/nodes/{node}/summary`, `runs://{run_id}/timeline`, `runs://{run_id}/errors`.
- New dependency: `rosbags` (pure Python, zero ROS2 deps).
- 171 tests (up from 125).

## [0.2.0] - 2026-03-14

### Added
- Custom log format support via `RCUTILS_CONSOLE_OUTPUT_FORMAT` environment variable.
- `LogEntry` extended with optional `function_name`, `source_code_file`, and `source_code_line` fields.
- 16 new tests (125 total).

### Changed
- Graceful fallbacks when format fields are missing (node name inferred from filename, timestamp defaults to 0.0).

## [0.1.0] - 2026-03-14

Initial release.

- Log file parsing with merged multi-node timelines.
- `list_runs`, `load_run`, `query_logs`, `get_node_summary`, `get_timeline`, `compare_runs` tools.
- Log path resolution via `MCP_ROS2_LOGS_DIR`, `ROS_LOG_DIR`, `ROS_HOME`, `~/.ros/log`.
- 109 tests.

[Unreleased]: https://github.com/spanchal001/mcp-ros2-logs/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/spanchal001/mcp-ros2-logs/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/spanchal001/mcp-ros2-logs/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/spanchal001/mcp-ros2-logs/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/spanchal001/mcp-ros2-logs/releases/tag/v0.1.0
