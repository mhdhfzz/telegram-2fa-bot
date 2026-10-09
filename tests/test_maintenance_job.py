from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from bot import maintenance_job_callback


@pytest.mark.asyncio
async def test_maintenance_job_callback():
    context = MagicMock()
    context.bot_data = {
        "engine": MagicMock(),
        "session_factory": MagicMock(),
        "mini_app_runner": MagicMock(),
        "settings": MagicMock(log_retention_days=30),
    }

    with patch("bot.run_full_maintenance", new_callable=AsyncMock) as mock_maint:
        mock_maint.return_value = {"deleted_logs": 5, "wal_checkpoint": True, "sessions_cleaned": True}
        await maintenance_job_callback(context)
        mock_maint.assert_called_once()
