import ctypes
from datetime import datetime, timedelta, timezone
import gc
import logging
import sys
from typing import Any, Dict, Optional
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from db.models import AccessLog

logger = logging.getLogger(__name__)


async def purge_old_access_logs(
    session_factory: async_sessionmaker[AsyncSession],
    retention_days: int = 30,
) -> int:
    """Hapus entri access_log yang lebih tua dari batas retensi hari."""
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    async with session_factory() as session:
        stmt = delete(AccessLog).where(AccessLog.created_at < cutoff)
        result = await session.execute(stmt)
        await session.commit()
        deleted_count = result.rowcount or 0
        if deleted_count > 0:
            logger.info("Purged %d stale audit logs older than %d days.", deleted_count, retention_days)
        return deleted_count


async def checkpoint_wal(engine: AsyncEngine) -> None:
    """Jalankan WAL checkpoint TRUNCATE untuk meratakan dan memangkas file -wal."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
            logger.info("Executed SQLite PRAGMA wal_checkpoint(TRUNCATE) successfully.")
    except Exception as exc:
        logger.warning("Error running wal_checkpoint: %s", exc)


def trim_memory() -> None:
    """Jalankan garbage collection Python dan lepaskan memori glibc ke OS kernel di Linux."""
    try:
        collected = gc.collect()
        trimmed = False
        if sys.platform.startswith("linux"):
            try:
                libc = ctypes.CDLL("libc.so.6")
                if hasattr(libc, "malloc_trim"):
                    libc.malloc_trim(0)
                    trimmed = True
            except Exception:
                pass
        logger.debug("Memory trimmed: gc_collected=%d, malloc_trimmed=%s", collected, trimmed)
    except Exception as exc:
        logger.warning("Error in trim_memory: %s", exc)


async def run_full_maintenance(
    engine: Optional[AsyncEngine],
    session_factory: Optional[async_sessionmaker[AsyncSession]],
    mini_app_runner: Optional[Any] = None,
    application: Optional[Any] = None,
    retention_days: int = 30,
) -> Dict[str, Any]:
    """Eksekusi seluruh siklus pemeliharaan: log pruning, WAL checkpoint, sesi, dan RAM trim."""
    stats = {
        "deleted_logs": 0,
        "wal_checkpoint": False,
        "sessions_cleaned": False,
    }

    if session_factory:
        try:
            stats["deleted_logs"] = await purge_old_access_logs(session_factory, retention_days)
        except Exception as exc:
            logger.warning("Failed to purge old logs: %s", exc)

    if engine:
        try:
            await checkpoint_wal(engine)
            stats["wal_checkpoint"] = True
        except Exception as exc:
            logger.warning("Failed to checkpoint WAL: %s", exc)

    if mini_app_runner and hasattr(mini_app_runner, "session_manager") and mini_app_runner.session_manager:
        try:
            mini_app_runner.session_manager.cleanup_expired()
            stats["sessions_cleaned"] = True
        except Exception as exc:
            logger.warning("Failed to clean mini app sessions: %s", exc)

    trim_memory()
    return stats
