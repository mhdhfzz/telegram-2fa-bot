import math
from typing import List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import AccessLog


async def log_action(
    session: AsyncSession,
    user_id: int,
    action: str,
    success: bool,
    account_id: Optional[int] = None,
) -> None:
    """Record an audit event without logging sensitive data (PINs, secrets, or OTPs)."""
    log_entry = AccessLog(
        user_id=user_id,
        account_id=account_id,
        action=action,
        success=success,
    )
    session.add(log_entry)
    await session.commit()


async def get_user_logs(
    session: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 10,
) -> Tuple[List[AccessLog], int]:
    """
    Get paginated access logs for a specific user, sorted from newest to oldest.
    Returns:
        (logs: list[AccessLog], total_pages: int)
    """
    # Count total entries
    count_query = select(func.count(AccessLog.id)).where(AccessLog.user_id == user_id)
    count_res = await session.execute(count_query)
    total_count = count_res.scalar_one()

    page_size = max(1, page_size) if isinstance(page_size, int) and page_size > 0 else 10
    total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
    page = max(1, min(page, total_pages)) if isinstance(page, int) else 1

    offset = (page - 1) * page_size
    query = (
        select(AccessLog)
        .where(AccessLog.user_id == user_id)
        .order_by(AccessLog.created_at.desc(), AccessLog.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    res = await session.execute(query)
    logs = list(res.scalars().all())

    return logs, total_pages
