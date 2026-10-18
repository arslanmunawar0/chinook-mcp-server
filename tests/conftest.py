from pathlib import Path

import pytest

from chinook_mcp.database import ReadOnlyDatabase

DB_PATH = Path(__file__).resolve().parents[1] / "chinook.db"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def db():
    database = ReadOnlyDatabase(DB_PATH)
    yield database
    database.close()
