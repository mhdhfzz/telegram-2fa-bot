import pytest
from sqlalchemy import text
from db.session import get_async_engine


@pytest.mark.asyncio
async def test_sqlite_pragmas_applied(tmp_path):
    db_file = tmp_path / "test_pragma.db"
    engine = get_async_engine(str(db_file))

    async with engine.connect() as conn:
        res = await conn.execute(text("PRAGMA cache_size"))
        cache_size = res.scalar()
        assert cache_size == -2000

        res = await conn.execute(text("PRAGMA synchronous"))
        sync_mode = res.scalar()
        # NORMAL mode is 1
        assert sync_mode == 1

        res = await conn.execute(text("PRAGMA temp_store"))
        temp_store = res.scalar()
        # MEMORY mode is 2
        assert temp_store == 2

        res = await conn.execute(text("PRAGMA mmap_size"))
        mmap_size = res.scalar()
        assert mmap_size == 0

    await engine.dispose()
