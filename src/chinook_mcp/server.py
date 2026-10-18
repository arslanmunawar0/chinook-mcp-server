"""MCP server that exposes a SQLite database to AI assistants, read-only."""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from chinook_mcp.database import (
    QueryError,
    QueryResult,
    ReadOnlyDatabase,
    TableDescription,
    TableSummary,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "chinook.db"

INSTRUCTIONS = """\
This server gives read-only access to the Chinook sample database: a digital
music store with artists, albums, tracks, playlists, customers, employees and
invoices. Start with list_tables or the chinook://schema resource, use
describe_table for column details and joins, then answer questions with
run_query. Only SELECT statements are allowed."""

_READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)


def create_server(db: ReadOnlyDatabase) -> MCPServer:
    server = MCPServer("chinook", instructions=INSTRUCTIONS)

    @server.tool(annotations=_READ_ONLY)
    def list_tables() -> list[TableSummary]:
        """List every table in the database with its row count."""
        return db.list_tables()

    @server.tool(annotations=_READ_ONLY)
    def describe_table(table: str) -> TableDescription:
        """Show a table's columns, primary key, foreign keys and row count."""
        try:
            return db.describe_table(table)
        except QueryError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(annotations=_READ_ONLY)
    def sample_rows(table: str, limit: int = 5) -> QueryResult:
        """Return the first few rows of a table to show what its data looks like."""
        try:
            return db.sample_rows(table, limit=limit)
        except QueryError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(annotations=_READ_ONLY)
    def run_query(sql: str, limit: int = 100) -> QueryResult:
        """Run one read-only SQL query (SQLite dialect) and return the rows.

        Only SELECT and WITH ... SELECT statements are accepted. At most `limit`
        rows are returned (1 to 1000); `truncated` is true when more rows
        matched, in which case narrow the query or aggregate instead.
        """
        try:
            return db.query(sql, limit=limit)
        except QueryError as exc:
            raise ToolError(str(exc)) from exc

    @server.resource(
        "chinook://schema",
        name="schema",
        description="CREATE statements for every table and index in the database.",
        mime_type="text/plain",
    )
    def schema() -> str:
        return db.schema_sql()

    return server


def main() -> None:
    db = ReadOnlyDatabase(os.environ.get("CHINOOK_DB_PATH", DEFAULT_DB_PATH))
    try:
        create_server(db).run()
    finally:
        db.close()


if __name__ == "__main__":
    main()
