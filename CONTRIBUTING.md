# Contributing to mcp-ros2-logs

## Development Setup

```bash
git clone https://github.com/spanchal001/mcp-ros2-logs.git
cd mcp-ros2-logs
pdm install
```

## Running Tests and Linting

```bash
pdm run pytest
pdm run ruff check src/ tests/
```

All tests must pass and ruff must report no issues before submitting a PR.

## Pull Request Workflow

1. Fork the repo and create a feature branch from `main`
2. Make your changes
3. Add tests for new functionality
4. Run `pdm run pytest` and `pdm run ruff check src/ tests/`
5. Commit with a concise message in imperative mood (e.g., "Add bag file filtering" not "Added bag file filtering")
6. Open a PR against `main`
7. CI must pass and at least one review approval is required before merging

## Code Style

- Python 3.10+ syntax (match/case, `X | Y` unions where appropriate)
- Type hints on all functions and class attributes
- Formatter: ruff, 88-character line limit
- No docstrings or comments on code you didn't change
- Prefer `pathlib` over `os.path`

## Project Structure

```
src/mcp_ros2_logs/
  server.py       — FastMCP server, tool and resource definitions
  parser.py       — Log file parsing, custom format support
  store.py        — In-memory cache for parsed runs and bags
  resolver.py     — Log path resolution (env vars, auto-detection)
  query.py        — Query engine, node summaries
  timeline.py     — Condensed narrative timeline
  compare.py      — Run-to-run comparison
  anomaly.py      — Statistical anomaly detection
  bag.py          — ROS2 bag file parsing (via rosbags)
  correlate.py    — Log-to-bag topic correlation
  tail.py         — Live log tailing
tests/
  fixtures/       — Synthetic ROS2 log files for testing
```

## Adding a New MCP Tool

1. Write the core logic in its own module under `src/mcp_ros2_logs/`
2. Add a `@mcp.tool()` decorated function in `server.py`
3. Add tests in `tests/test_<module>.py`
4. Update the Tools section in `README.md`
