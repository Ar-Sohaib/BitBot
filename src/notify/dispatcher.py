"""
Telegram notification dispatcher — rate limiting + idempotence.
Manages state to avoid sending duplicate or spammy notifications.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from src.storage.db import Database


class TelegramDispatcher:
    """
    Controls when to send notifications based on event type, rate limits, and state.
    """

    # Rate limits (seconds)
    RATE_LIMITS = {
        "startup": 6 * 3600,  # 1 per 6h
        "feed_down": 60,  # Only 1 when transition to DOWN
        "feed_ok": 60,  # Only 1 when transition to OK
        "wallet_low": 3600,  # 1 per hour while low
        "trade": 0,  # No rate limit (idempotent via trade_id)
        "daily_report": 86400,  # 1 per day
    }

    def __init__(self, db: Database, tz_name: str = "Europe/Paris"):
        self.db = db
        self.tz = ZoneInfo(tz_name)
        self.log = logging.getLogger("telegram_dispatcher")

    def should_send_startup(self) -> bool:
        """Check if enough time has passed since last startup notification."""
        last_ts_str = self.db.get_bot_state("last_startup_notif_ts")
        if not last_ts_str:
            return True
        last_ts = float(last_ts_str)
        now_ts = time.time()
        return (now_ts - last_ts) >= self.RATE_LIMITS["startup"]

    def mark_startup_sent(self) -> None:
        """Record startup notification timestamp."""
        self.db.set_bot_state("last_startup_notif_ts", str(time.time()))

    def should_send_feed_down(self) -> bool:
        """Send feed_down only on transition FROM ok TO down."""
        feed_status = self.db.get_bot_state("feed_status")
        return feed_status != "down"

    def mark_feed_down(self) -> None:
        """Record feed down state and timestamp."""
        self.db.set_bot_state("feed_status", "down")
        self.db.set_bot_state("feed_down_since_ts", str(int(datetime.now(tz=self.tz).timestamp() * 1000)))

    def should_send_feed_ok(self) -> bool:
        """Send feed_ok only on transition FROM down TO ok."""
        feed_status = self.db.get_bot_state("feed_status")
        return feed_status == "down"

    def mark_feed_ok(self) -> None:
        """Record feed recovered state."""
        self.db.set_bot_state("feed_status", "ok")
        self.db.set_bot_state("feed_down_since_ts", "")

    def get_feed_downtime_seconds(self) -> int:
        """Calculate seconds since feed went down."""
        down_ts_str = self.db.get_bot_state("feed_down_since_ts")
        if not down_ts_str:
            return 0
        down_ts_ms = float(down_ts_str)
        now_ms = datetime.now(tz=self.tz).timestamp() * 1000
        return int((now_ms - down_ts_ms) / 1000)

    def should_send_wallet_low(self) -> bool:
        """Check if wallet low alert should be sent (rate limited)."""
        last_ts_str = self.db.get_bot_state("last_wallet_low_notif_ts")
        if not last_ts_str:
            return True
        last_ts = float(last_ts_str)
        now_ts = time.time()
        return (now_ts - last_ts) >= self.RATE_LIMITS["wallet_low"]

    def mark_wallet_low_sent(self) -> None:
        """Record wallet low alert timestamp."""
        self.db.set_bot_state("last_wallet_low_notif_ts", str(time.time()))

    def should_send_daily_report(self, report_date: str) -> bool:
        """Send daily report only once per day."""
        last_date = self.db.get_bot_state("last_daily_report_date")
        return last_date != report_date

    def mark_daily_report_sent(self, report_date: str) -> None:
        """Record daily report date."""
        self.db.set_bot_state("last_daily_report_date", report_date)

    def should_send_trade(self, trade_id: str) -> bool:
        """Trades are sent once per trade_id (idempotent)."""
        key = f"trade_notif_{trade_id}"
        return self.db.get_bot_state(key) is None

    def mark_trade_sent(self, trade_id: str) -> None:
        """Record that this trade notification was sent."""
        key = f"trade_notif_{trade_id}"
        self.db.set_bot_state(key, "1")
