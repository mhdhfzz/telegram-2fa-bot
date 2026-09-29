from datetime import datetime, timedelta, timezone
from typing import Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User


def _to_utc(dt: datetime) -> datetime:
    """Ensure datetime has UTC timezone."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def check_lockout(user: User) -> Tuple[bool, int]:
    """
    Check if the user is currently locked out.
    Returns:
        (is_locked: bool, remaining_seconds: int)
    """
    if not user or not user.locked_until:
        return False, 0

    now = datetime.now(timezone.utc)
    locked_until_utc = _to_utc(user.locked_until)

    if locked_until_utc > now:
        remaining_seconds = int((locked_until_utc - now).total_seconds())
        return True, max(1, remaining_seconds)

    return False, 0


async def record_failed_pin_attempt(session: AsyncSession, user: User) -> Tuple[bool, int]:
    """
    Increment failed PIN attempts and apply lockout if threshold (5) is reached.
    Lockout duration escalation:
      5th attempt: 5 minutes (300s)
      6th attempt: 15 minutes (900s)
      >=7th attempt: 60 minutes (3600s)
    Returns:
        (is_locked: bool, remaining_seconds: int)
    """
    user.failed_pin_attempts += 1
    attempts = user.failed_pin_attempts

    if attempts >= 5:
        if attempts == 5:
            duration_seconds = 300  # 5 minutes
        elif attempts == 6:
            duration_seconds = 900  # 15 minutes
        else:
            duration_seconds = 3600  # 60 minutes cap

        now = datetime.now(timezone.utc)
        user.locked_until = now + timedelta(seconds=duration_seconds)
        await session.commit()
        return True, duration_seconds

    await session.commit()
    return False, 0


async def record_successful_pin_attempt(session: AsyncSession, user: User) -> None:
    """Reset failed attempts and clear lockout on valid PIN."""
    user.failed_pin_attempts = 0
    user.locked_until = None
    await session.commit()
