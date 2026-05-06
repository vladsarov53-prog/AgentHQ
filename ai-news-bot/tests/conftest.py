from __future__ import annotations

import pytest
import pytest_asyncio

from src.storage.database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    db_path = tmp_path / "test.db"
    database = await Database.create(db_path)
    yield database
    await database.close()
