import hashlib

import pytest

from chinook_mcp.database import QueryError, ReadOnlyDatabase
from conftest import DB_PATH


def test_lists_all_chinook_tables_with_row_counts(db):
    counts = {t.name: t.row_count for t in db.list_tables()}

    assert counts == {
        "Album": 347,
        "Artist": 275,
        "Customer": 59,
        "Employee": 8,
        "Genre": 25,
        "Invoice": 412,
        "InvoiceLine": 2240,
        "MediaType": 5,
        "Playlist": 18,
        "PlaylistTrack": 8715,
        "Track": 3503,
    }


def test_describes_columns_and_foreign_keys(db):
    album = db.describe_table("album")

    assert album.name == "Album"
    assert [c.name for c in album.columns] == ["AlbumId", "Title", "ArtistId"]
    assert album.columns[0].primary_key
    assert [(fk.column, fk.references_table, fk.references_column) for fk in album.foreign_keys] == [
        ("ArtistId", "Artist", "ArtistId")
    ]


def test_unknown_table_lists_the_valid_ones(db):
    with pytest.raises(QueryError, match="Unknown table 'Songs'.*Track"):
        db.describe_table("Songs")


def test_runs_a_join_and_reports_columns(db):
    result = db.query(
        """
        SELECT ar.Name AS artist, COUNT(*) AS albums
        FROM Album al JOIN Artist ar ON ar.ArtistId = al.ArtistId
        GROUP BY ar.ArtistId ORDER BY albums DESC, artist LIMIT 1
        """
    )

    assert result.columns == ["artist", "albums"]
    assert result.rows == [["Iron Maiden", 21]]
    assert not result.truncated


def test_accepts_common_table_expressions(db):
    result = db.query("WITH g AS (SELECT * FROM Genre) SELECT COUNT(*) FROM g;")

    assert result.rows == [[25]]


def test_truncates_to_the_row_limit(db):
    result = db.query("SELECT TrackId FROM Track ORDER BY TrackId", limit=3)

    assert result.rows == [[1], [2], [3]]
    assert result.row_count == 3
    assert result.truncated


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM Artist",
        "UPDATE Artist SET Name = 'x'",
        "INSERT INTO Genre (GenreId, Name) VALUES (999, 'x')",
        "DROP TABLE Artist",
        "CREATE TABLE t (x)",
        "PRAGMA writable_schema = ON",
        "ATTACH DATABASE ':memory:' AS other",
        "WITH x AS (SELECT 1) DELETE FROM Artist",
    ],
)
def test_rejects_anything_that_is_not_a_read(db, sql):
    with pytest.raises(QueryError):
        db.query(sql)


def test_rejects_multiple_statements(db):
    with pytest.raises(QueryError, match="one statement"):
        db.query("SELECT 1; DELETE FROM Artist")


def test_reports_sql_errors(db):
    with pytest.raises(QueryError, match="no such table"):
        db.query("SELECT * FROM Songs")


@pytest.mark.parametrize("limit", [0, 1001])
def test_rejects_out_of_range_limits(db, limit):
    with pytest.raises(QueryError, match="limit"):
        db.query("SELECT 1", limit=limit)


def test_stops_queries_that_run_too_long():
    database = ReadOnlyDatabase(DB_PATH, timeout_seconds=0.2)
    try:
        with pytest.raises(QueryError, match="time limit"):
            database.query(
                "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) "
                "SELECT COUNT(*) FROM n"
            )
    finally:
        database.close()


def test_schema_contains_create_statements(db):
    schema = db.schema_sql()

    assert 'CREATE TABLE [Album]' in schema or 'CREATE TABLE "Album"' in schema
    assert "CREATE INDEX" in schema


def test_database_file_is_never_modified(db):
    before = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()
    for sql in ("DELETE FROM Artist", "DROP TABLE Track"):
        with pytest.raises(QueryError):
            db.query(sql)

    assert hashlib.sha256(DB_PATH.read_bytes()).hexdigest() == before
