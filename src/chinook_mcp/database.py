"""Read-only access to a SQLite database."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from pydantic import BaseModel

MAX_ROW_LIMIT = 1000

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


class QueryError(ValueError):
    """Raised when a query is rejected or fails."""


class TableSummary(BaseModel):
    name: str
    row_count: int


class Column(BaseModel):
    name: str
    type: str
    not_null: bool
    primary_key: bool
    default: str | None


class ForeignKey(BaseModel):
    column: str
    references_table: str
    references_column: str


class TableDescription(BaseModel):
    name: str
    row_count: int
    columns: list[Column]
    foreign_keys: list[ForeignKey]


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[str | int | float | None]]
    row_count: int
    truncated: bool


class ReadOnlyDatabase:
    """A SQLite database that can only be read.

    The file is opened in read-only mode, and user queries additionally run
    under an authorizer that allows nothing but reads, so writes, PRAGMAs and
    ATTACH are refused by SQLite itself rather than by string matching.
    """

    def __init__(self, path: str | Path, *, timeout_seconds: float = 5.0) -> None:
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"Database not found: {self.path}")
        self.timeout_seconds = timeout_seconds
        self._conn = sqlite3.connect(
            f"{self.path.as_uri()}?mode=ro", uri=True, check_same_thread=False
        )
        self._conn.execute("PRAGMA query_only = ON")

    def close(self) -> None:
        self._conn.close()

    def table_names(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [name for (name,) in rows]

    def list_tables(self) -> list[TableSummary]:
        return [
            TableSummary(name=name, row_count=self._row_count(name))
            for name in self.table_names()
        ]

    def describe_table(self, table: str) -> TableDescription:
        name = self._resolve_table(table)
        columns = [
            Column(
                name=col_name,
                type=col_type,
                not_null=bool(not_null),
                primary_key=bool(pk),
                default=default,
            )
            for _, col_name, col_type, not_null, default, pk in self._conn.execute(
                f"PRAGMA table_info({_quote(name)})"
            )
        ]
        foreign_keys = [
            ForeignKey(column=row[3], references_table=row[2], references_column=row[4])
            for row in self._conn.execute(f"PRAGMA foreign_key_list({_quote(name)})")
        ]
        return TableDescription(
            name=name,
            row_count=self._row_count(name),
            columns=columns,
            foreign_keys=foreign_keys,
        )

    def sample_rows(self, table: str, limit: int = 5) -> QueryResult:
        name = self._resolve_table(table)
        return self.query(f"SELECT * FROM {_quote(name)}", limit=limit)

    def schema_sql(self) -> str:
        rows = self._conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
            "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, name"
        ).fetchall()
        return ";\n\n".join(sql for (sql,) in rows) + ";\n"

    def query(self, sql: str, limit: int = 100) -> QueryResult:
        """Run a single read-only statement and return at most `limit` rows."""
        if not 1 <= limit <= MAX_ROW_LIMIT:
            raise QueryError(f"limit must be between 1 and {MAX_ROW_LIMIT}")
        sql = sql.strip().rstrip(";").strip()
        if not sql:
            raise QueryError("Query is empty")

        deadline = time.monotonic() + self.timeout_seconds
        self._conn.set_authorizer(_authorize_read_only)
        self._conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
        try:
            cursor = self._conn.execute(sql)
            if cursor.description is None:
                raise QueryError("Only queries that return rows are allowed")
            rows = cursor.fetchmany(limit + 1)
        except sqlite3.DatabaseError as exc:
            if "interrupted" in str(exc):
                raise QueryError(
                    f"Query exceeded the {self.timeout_seconds:g}s time limit"
                ) from exc
            if "not authorized" in str(exc):
                raise QueryError("Only read-only SELECT queries are allowed") from exc
            raise QueryError(str(exc)) from exc
        finally:
            self._conn.set_authorizer(None)
            self._conn.set_progress_handler(None, 0)

        truncated = len(rows) > limit
        rows = rows[:limit]
        return QueryResult(
            columns=[col[0] for col in cursor.description],
            rows=[[_json_value(v) for v in row] for row in rows],
            row_count=len(rows),
            truncated=truncated,
        )

    def _resolve_table(self, table: str) -> str:
        names = {name.lower(): name for name in self.table_names()}
        try:
            return names[table.lower()]
        except KeyError:
            raise QueryError(
                f"Unknown table {table!r}. Available tables: {', '.join(names.values())}"
            ) from None

    def _row_count(self, table: str) -> int:
        (count,) = self._conn.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()
        return count


def _authorize_read_only(action: int, *_: object) -> int:
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _json_value(value: object) -> str | int | float | None:
    if isinstance(value, bytes):
        return value.hex()
    return value  # type: ignore[return-value]
