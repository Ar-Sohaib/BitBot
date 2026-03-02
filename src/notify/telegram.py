from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from src.models import DailyReport, TradeResult
from src.analytics.daily_report import render_daily_report_text


class TelegramNotifier:
    def __init__(self, enabled: bool, bot_token: str, chat_id: str, tz_name: str = "Europe/Paris", timeout_seconds: int = 10):
        self.enabled = enabled and bool(bot_token) and bool(chat_id)
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.tz = ZoneInfo(tz_name)
        self.timeout_seconds = timeout_seconds
        self.log = logging.getLogger("telegram")
        self._feed_error_notified = False

    def send_message(self, text: str) -> None:
        if not self.enabled:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}

        attempts = 3
        for i in range(attempts):
            try:
                r = requests.post(url, json=payload, timeout=self.timeout_seconds)
                r.raise_for_status()
                return
            except Exception as exc:
                self.log.warning("Telegram send failed attempt=%s err=%s", i + 1, exc)
                if i < attempts - 1:
                    time.sleep(1.5 * (i + 1))

    def notify_trade(self, trade: TradeResult, market_price: float, cash: float, btc_qty: float, slippage_rate: float = 0.0002) -> None:
        if not trade.executed or trade.side is None:
            return
        now_str = datetime.now(tz=self.tz).strftime("%Y-%m-%d %H:%M:%S")
        slip_pct = slippage_rate * 100
        text = (
            f"[PAPER][BTC] {trade.side} exécuté\n"
            f"Time: {now_str}\n"
            f"Market: {market_price:.1f}\n"
            f"Exec: {trade.price_exec:.1f} (slip {slip_pct:.2f}%)\n"
            f"Qty: {trade.qty_btc:.5f} BTC\n"
            f"Fee: {trade.fee:.2f} USDT\n"
            f"Wallet: cash={cash:.1f} | btc={btc_qty:.5f}\n"
            f"Reason: {trade.reason}"
        )
        self.send_message(text)

    def notify_kill_switch(self, drawdown: float, threshold: float, equity: float) -> None:
        text = (
            f"[ALERT][PAPER][BTC] Kill switch déclenché\n"
            f"Drawdown: {drawdown:.1%} (seuil {threshold:.0%})\n"
            f"Action: Trading stoppé (no new orders)\n"
            f"Equity: {equity:.1f}"
        )
        self.send_message(text)

    def notify_feed_down(self, error: str) -> None:
        if self._feed_error_notified:
            return
        self._feed_error_notified = True
        self.send_message(f"[ALERT][PAPER][BTC] Feed prix down\nError: {error}")

    def notify_feed_recovered(self) -> None:
        if self._feed_error_notified:
            self._feed_error_notified = False
            self.send_message("[INFO][PAPER][BTC] Feed prix rétabli")

    def notify_bot_start(self, symbol: str, timeframe: str) -> None:
        now_str = datetime.now(tz=self.tz).strftime("%Y-%m-%d %H:%M:%S")
        self.send_message(f"[INFO][PAPER][BTC] Bot démarré\nTime: {now_str}\nSymbol: {symbol} {timeframe}")

    def notify_daily_report(self, report: DailyReport) -> None:
        self.send_message(render_daily_report_text(report))

    def notify_alert(self, text: str) -> None:
        self.send_message(f"[ALERT][PAPER][BTC] {text}")
