# Chinook MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server, written in Python, that lets AI assistants such as Cursor and Claude Desktop explore and query a SQLite database in plain English. The database is **read-only**, so the assistant can't change your data.

It ships with the [Chinook sample database](https://github.com/lerocha/chinook-database), a digital music store with artists, albums, tracks, customers, employees and invoices. Point it at any other SQLite file with one environment variable.

Ask things like:

- "Which five artists earned the most revenue, and in which countries do their customers live?"
- "Which sales agent had the highest sales in 2013?"
- "Show me the schema and explain how invoices link to tracks."

The assistant reads the schema, writes the SQL, runs it through this server and explains the result.

## Tools

| Tool | What it does |
| --- | --- |
| `list_tables` | Lists every table with its row count. |
| `describe_table` | Shows columns, types, primary key, foreign keys and row count. |
| `sample_rows` | Returns the first few rows of a table. |
| `run_query` | Runs one read-only SQL query and returns columns and rows (up to 1,000). |

The `chinook://schema` resource holds the full `CREATE` statements. All tools return structured JSON output and are marked read-only for MCP clients.

## How it stays read-only

Safety is enforced by SQLite itself, not by matching keywords in the SQL:

- The file is opened in read-only mode (`mode=ro`) with `PRAGMA query_only`.
- Every query runs under a SQLite **authorizer** that allows reads only. `INSERT`, `UPDATE`, `DELETE`, DDL, `PRAGMA` and `ATTACH` are refused, even when hidden inside a `WITH` clause.
- Only one statement is allowed per call.
- Results are capped by a row limit, and a time limit (5 seconds by default) stops runaway queries.
- Table names passed to `describe_table` and `sample_rows` are checked against the real table list.

## Setup

Requires Python 3.10 or newer.

```bash
git clone https://github.com/arslanmunawar0/chinook-mcp-server.git
cd chinook-mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Connect it to an assistant

Use the absolute path to the `chinook-mcp-server` command inside your virtual environment.

**Cursor**: add this to `.cursor/mcp.json` in your project, or to `~/.cursor/mcp.json` to use it everywhere.

```json
{
  "mcpServers": {
    "chinook": {
      "command": "/absolute/path/to/chinook-mcp-server/.venv/bin/chinook-mcp-server"
    }
  }
}
```

**Claude Desktop**: add the same `mcpServers` block to `claude_desktop_config.json` and restart the app.

**MCP Inspector**: to try the tools in a browser:

```bash
npx @modelcontextprotocol/inspector .venv/bin/chinook-mcp-server
```

### Using your own database

Set `CHINOOK_DB_PATH` to any SQLite file:

```json
{
  "mcpServers": {
    "my-data": {
      "command": "/absolute/path/to/chinook-mcp-server/.venv/bin/chinook-mcp-server",
      "env": { "CHINOOK_DB_PATH": "/absolute/path/to/your.db" }
    }
  }
}
```

## Project layout

```
src/chinook_mcp/database.py   read-only SQLite access (authorizer, limits, schema)
src/chinook_mcp/server.py     MCP tools and resource
tests/                        database tests, plus end-to-end tests over the MCP protocol and stdio
chinook.db                    Chinook sample database, v1.4.5
```

Built with the official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) (v2).

## Credits and licence

`chinook.db` is the [Chinook Database](https://github.com/lerocha/chinook-database) by Luis Rocha, file `Chinook_Sqlite.sqlite` from release [v1.4.5](https://github.com/lerocha/chinook-database/releases/tag/v1.4.5). It is used under the MIT licence, included unchanged in [LICENSE-CHINOOK.md](LICENSE-CHINOOK.md).

The server code is MIT-licensed; see [LICENSE](LICENSE).
