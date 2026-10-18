import sys

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from chinook_mcp.server import create_server
from conftest import DB_PATH

pytestmark = pytest.mark.anyio


async def test_exposes_read_only_tools(db):
    async with Client(create_server(db)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    assert set(tools) == {"list_tables", "describe_table", "sample_rows", "run_query"}
    for tool in tools.values():
        assert tool.description
        assert tool.annotations.read_only_hint
        assert tool.output_schema


async def test_run_query_returns_structured_rows(db):
    async with Client(create_server(db)) as client:
        result = await client.call_tool(
            "run_query",
            {"sql": "SELECT Name FROM Genre ORDER BY GenreId", "limit": 2},
        )

    assert not result.is_error
    assert result.structured_content == {
        "columns": ["Name"],
        "rows": [["Rock"], ["Jazz"]],
        "row_count": 2,
        "truncated": True,
    }


async def test_rejected_query_comes_back_as_a_tool_error(db):
    async with Client(create_server(db)) as client:
        result = await client.call_tool("run_query", {"sql": "DROP TABLE Artist"})

    assert result.is_error
    assert "Only read-only SELECT queries are allowed" in result.content[0].text


async def test_describe_and_sample_table(db):
    async with Client(create_server(db)) as client:
        described = await client.call_tool("describe_table", {"table": "Track"})
        sample = await client.call_tool("sample_rows", {"table": "Track", "limit": 1})

    assert described.structured_content["row_count"] == 3503
    assert sample.structured_content["rows"][0][1] == "For Those About To Rock (We Salute You)"


async def test_schema_resource(db):
    async with Client(create_server(db)) as client:
        resources = (await client.list_resources()).resources
        contents = (await client.read_resource("chinook://schema")).contents

    assert [str(r.uri) for r in resources] == ["chinook://schema"]
    assert "InvoiceLine" in contents[0].text


async def test_runs_over_stdio_as_a_subprocess():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "chinook_mcp.server"],
        env={"CHINOOK_DB_PATH": str(DB_PATH)},
    )
    async with Client(params) as client:
        result = await client.call_tool("list_tables", {})

    assert len(result.structured_content["result"]) == 11
