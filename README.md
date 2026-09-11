# KGP Campus Intelligence MCP Server

A stateless, protocol-native interface exposing IIT Kharagpur campus data
(academics, events, locations, halls) to AI clients via the Model Context Protocol.

## Status: Week 1 — Server Skeleton

- [x] FastMCP server running over STDIO
- [x] `CampusEntity` schema defined
- [x] `SourceAdapter` interface defined
- [x] Placeholder `search_courses` tool with dummy data
- [x] pytest suite (5 tests)
- [x] GitHub Actions CI (lint + type check + test)

## Quickstart

```bash
# Install dependencies
uv sync

# Run the server over STDIO
uv run python src/kgp_mcp/server.py

# Run tests
uv run pytest -v
