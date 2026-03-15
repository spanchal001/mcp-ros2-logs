# mcp-ros2-logs

An MCP server that gives AI agents the ability to analyze ROS2 log files across multiple nodes. It solves the core pain point of ROS2's fragmented logging — where each node writes to its own separate file — by merging them into a unified timeline and exposing smart query tools.

**No ROS2 installation required.** It just reads log files from disk.

## Install

```bash
pipx install mcp-ros2-logs
```

Or with pip (in a virtual environment):

```bash
pip install mcp-ros2-logs
```

Or from source:

```bash
git clone https://github.com/spanchal001/mcp-ros2-logs.git
cd mcp-ros2-logs
pdm install
```

## Setup

### Claude Code

```bash
claude mcp add --scope user ros2-logs -- mcp-ros2-logs
```

This makes the server available in all Claude Code sessions. For project-scoped setup (current directory only), omit `--scope user`.

To set a custom log directory:

```bash
claude mcp add --scope user ros2-logs -e MCP_ROS2_LOGS_DIR=/path/to/logs -- mcp-ros2-logs
```

### Claude Desktop

Add to `~/.config/Claude/claude_desktop_config.json` (Linux) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "ros2-logs": {
      "command": "mcp-ros2-logs",
      "env": {
        "MCP_ROS2_LOGS_DIR": "/path/to/your/ros2/logs"
      }
    }
  }
}
```

### VS Code (GitHub Copilot)

Add to `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "ros2-logs": {
      "command": "mcp-ros2-logs",
      "env": {
        "MCP_ROS2_LOGS_DIR": "/path/to/your/ros2/logs"
      }
    }
  }
}
```

Then use Copilot in agent mode (`@workspace`) to query your logs.

### Cursor

Open **Settings > MCP Servers > Add Server** and configure:

```json
{
  "ros2-logs": {
    "command": "mcp-ros2-logs",
    "env": {
      "MCP_ROS2_LOGS_DIR": "/path/to/your/ros2/logs"
    }
  }
}
```

## Tools

### list_runs

Discover available log runs in the log directory.

```
"list my ROS2 log runs"
"list runs in /tmp/robot_logs"
```

### load_run

Parse all log files in a run into a merged, sorted timeline.

```
"load the latest run"
"load bad_run from /tmp/robot_logs"
```

### query_logs

Search and filter the merged timeline. Supports severity, node, time range, text, and context window filters.

```
"show me all errors and fatals"
"find messages containing 'timeout' from sensor_driver"
"show errors with 5 messages of context around each match"
"show warnings in the last 30 seconds of the run"
```

### get_node_summary

Detailed analysis of a specific node: uptime, severity counts, recurring message patterns, unique errors, stack traces, and message rate.

```
"summarize the sensor_driver node"
"what errors did motion_planner have?"
```

### get_timeline

Condensed narrative of a run. Groups consecutive messages, highlights severity transitions (INFO -> ERROR), and flags gaps where nodes went silent.

```
"show me a timeline of the run"
"what's the timeline for the last 10 seconds?"
```

### compare_runs

Diff two runs to find what changed. Shows new/missing nodes, severity distribution changes, novel error messages, first divergence point, and timing differences.

```
"compare good_run vs bad_run"
"what's different between yesterday's run and today's?"
```

### detect_anomalies

Statistically flags unusual patterns using the first portion of a run as a baseline. Detects rate spikes, new error patterns, severity escalations, silence gaps, and error bursts.

```
"detect anomalies in bad_run"
"find anomalies with severity score above 0.5"
```

### list_bag_topics

List topics in a ROS2 bag file (.db3/.mcap) with message types and counts. No ROS2 installation or message deserialization needed.

```
"list bag topics in my_recording"
```

### query_bag_messages

Query bag messages filtered by topic and time range. Shows timestamps, topic names, message types, and sizes.

```
"show messages from /scan topic in my_recording"
"query bag messages from the last 10 seconds"
```

### correlate

Cross-reference log entries with bag topic messages within a time window. Shows what was happening on ROS2 topics around errors. Can correlate logs from one run with a bag from a different run.

```
"correlate errors in bad_run with bag from bag_recording"
"correlate errors with bag topics, 500ms window"
```

### tail_logs

Tail a log run for new entries since the last check. First call loads the run, subsequent calls return only new entries. Useful for monitoring an active ROS2 system.

```
"tail my_live_run"
"check for new log entries"
```

## MCP Resources

The server also exposes log data as browsable MCP resources:

| URI | Description |
|-----|-------------|
| `runs://list` | List of available runs |
| `runs://{run_id}/summary` | Run overview (nodes, severity counts, time range) |
| `runs://{run_id}/nodes/{node}/summary` | Per-node detailed summary |
| `runs://{run_id}/timeline` | Condensed narrative timeline |
| `runs://{run_id}/errors` | All ERROR/FATAL entries |

## Log Path Resolution

The server resolves the log directory using this priority chain:

1. `log_dir` parameter on the tool call
2. `MCP_ROS2_LOGS_DIR` env var
3. `ROS_LOG_DIR` env var
4. `$ROS_HOME/log/`
5. `~/.ros/log/`

It auto-detects whether a path is a single log file, a run directory (contains `.log` files), a bag directory (contains `metadata.yaml`), or a log root (contains run subdirectories).

## Log Format

Parses the standard ROS2 spdlog default format:

```
[SEVERITY] [EPOCH.NANOSECONDS] [node_name]: message
```

Example:

```
[INFO] [1713099970.190824925] [talker_node]: Publishing: Hello World 1
[WARN] [1713099975.443210100] [motion_planner]: Planning timeout after 500ms
[ERROR] [1713099975.501332000] [collision_checker]: No valid trajectory found
```

Multi-line messages (stack traces) are handled automatically.

### Custom Log Formats

If your ROS2 nodes use a custom `RCUTILS_CONSOLE_OUTPUT_FORMAT`, pass it as an environment variable when registering the MCP server:

```bash
claude mcp add --scope user ros2-logs \
  -e RCUTILS_CONSOLE_OUTPUT_FORMAT="{severity} {time} {name}: {message}" \
  -- mcp-ros2-logs
```

Or for Claude Desktop, add it to the `env` block:

```json
{
  "mcpServers": {
    "ros2-logs": {
      "command": "mcp-ros2-logs",
      "env": {
        "RCUTILS_CONSOLE_OUTPUT_FORMAT": "{severity} {time} {name}: {message}"
      }
    }
  }
}
```

Supported placeholders: `{severity}`, `{time}`, `{name}`, `{message}`, `{function_name}`, `{file_name}`, `{line_number}`.

When `{name}` is absent from the format, the node name is inferred from the log filename. When `{time}` is absent, entries are ordered by their position in the file.

## Development

```bash
git clone https://github.com/spanchal001/mcp-ros2-logs.git
cd mcp-ros2-logs
pdm install
pdm run pytest
pdm run ruff check src/ tests/
```

## License

MIT
