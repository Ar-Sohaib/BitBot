"""
Telegram notification formatting and sending.

Separates message formatting (templates) from dispatch rules (anti-spam).
All templates follow directive: readable in < 2 seconds, Markdown simple, French.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from src.models import DailyReport, TradeResult


class TelegramNotifier:
    """Sends formatted messages to Telegram via Bot API."""

    def __init__(self, enabled: bool, bot_token: str, chat_id: str, tz_name: str = "Europe/Paris", timeout_seconds: int = 10):
        self.enabled = enabled and bool(bot_token) and bool(chat_id)
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.tz = ZoneInfo(tz_name)
        self.timeout_seconds = timeout_seconds
        self.log = logging.getLogger("telegram")
        
        if not self.enabled:
            self.log.warning("TelegramNotifier disabled: enabled=%s bot_token_provided=%s chat_id_provided=%s",
                             enabled, bool(bot_token), bool(chat_id))

    def _now_label(self) -> str:
        """Return current time as 'HH:MM:SS | YYYY-MM-DD'."""
        return datetime.now(tz=self.tz).strftime("%H:%M:%S | %Y-%m-%d")

    def send_message(self, text: str) -> bool:
        """
        Send a message to Telegram with retry logic.
        Returns True if successful, False otherwise.
        """
        if not self.enabled:
            return False
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                r = requests.post(url, json=payload, timeout=self.timeout_seconds)
                if r.status_code == 200:
                    self.log.debug("Telegram message sent successfully")
                    return True
                else:
                    self.log.warning(f"Telegram API returned {r.status_code}: {r.text}")
                    if attempt < max_retries - 1:
                        wait_time = 1.5 ** (attempt + 1)
                        self.log.debug(f"Retrying in {wait_time}s...")
                        time.sleep(wait_time)
            except Exception as exc:
                self.log.error(f"Failed to send Telegram message: {exc}")
                if attempt < max_retries - 1:
                    wait_time = 1.5 ** (attempt + 1)
                    self.log.debug(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)

        self.log.error(f"Failed to send Telegram message after {max_retries} attempts")
        return False

    # ============================================================================
    # Format functions — each returns a ready-to-send Telegram Markdown message
    # ============================================================================

    def format_startup(self, symbol: str, timeframe: str, source: str, version: str = "",
                      db_name: str = "") -> str:
        """Format STARTUP message (once per 6h)."""
        timestamp = self._now_label()
        extra = ""
        if version:
            extra += f" | Version: `{version}`"
        if db_name:
            extra += f" | DB: `{db_name}`"
        
        text = f"""**🟢 BitBot — DÉMARRÉ**
`{symbol} • {timeframe} • Europe/Paris`
⏱️ `{timestamp}`
Mode: `LIVE` | Source: `{source}`{extra}"""
        return text

    def format_trade_buy(self, symbol: str, market_price: float, exec_price: float,
                        qty: float, fee: float, wallet_cash: float, wallet_btc: float,
                        equity: float, reason: str) -> str:
        """Format TRADE_BUY message (per trade)."""
        timestamp = self._now_label()
        slippage_pct = abs(exec_price - market_price) / market_price * 100 if market_price > 0 else 0
        
        text = f"""**✅ BUY — {symbol} (PAPER)**
⏱️ `{timestamp}`
Prix: `{market_price:.2f}` → `{exec_price:.2f}` (slip `{slippage_pct:.2f}%`)
Taille: `{qty:.6f} BTC` | Fee: `{fee:.2f} USDT`
Wallet: `{wallet_cash:.2f} USDT` + `{wallet_btc:.6f} BTC` | Eq: `{equity:.2f}`
Signal: {reason}"""
        return text

    def format_trade_sell(self, symbol: str, market_price: float, exec_price: float,
                         qty: float, fee: float, wallet_cash: float, wallet_btc: float,
                         equity: float, pnl_trade_abs: float = 0.0, pnl_trade_pct: float = 0.0,
                         pnl_day_abs: float = 0.0, reason: str = "") -> str:
        """Format TRADE_SELL message with PnL (per trade)."""
        timestamp = self._now_label()
        slippage_pct = abs(exec_price - market_price) / market_price * 100 if market_price > 0 else 0
        
        pnl_line = f"PnL trade: `{pnl_trade_abs:+.2f} USDT` (`{pnl_trade_pct:+.2f}%`)"
        if pnl_day_abs != 0.0:
            pnl_line += f" | Day: `{pnl_day_abs:+.2f}`"
        
        text = f"""**✅ SELL — {symbol} (PAPER)**
⏱️ `{timestamp}`
Prix: `{market_price:.2f}` → `{exec_price:.2f}` (slip `{slippage_pct:.2f}%`)
Taille: `{qty:.6f} BTC` | Fee: `{fee:.2f} USDT`
{pnl_line}
Wallet: `{wallet_cash:.2f} USDT` + `{wallet_btc:.6f} BTC` | Eq: `{equity:.2f}`
Signal: {reason}"""
        return text

    def format_kill_switch(self, drawdown: float, threshold: float, equity: float,
                          position_btc: float) -> str:
        """Format KILL_SWITCH message (once per incident)."""
        timestamp = self._now_label()
        position_str = f"`{position_btc:.6f} BTC`" if position_btc > 0 else "`Flat`"
        
        text = f"""**🔴 KILL SWITCH — TRADING STOP**
⏱️ `{timestamp}`
Drawdown: `{drawdown:.2f}%` (seuil `{threshold:.2f}%`)
Equity: `{equity:.2f} USDT`
Position: {position_str}
Action: Aucun nouvel ordre"""
        return text

    def format_feed_down(self, provider: str, error_msg: str, retry_count: int,
                        backoff_sec: float, trading_paused: bool) -> str:
        """Format FEED_DOWN message (once per incident after N errors)."""
        timestamp = self._now_label()
        pause_status = "`Pause trading`" if trading_paused else "`Monitoring`"
        
        text = f"""**⚠️ DATA FEED DOWN — {provider}**
⏱️ `{timestamp}`
Erreur: {error_msg}
Retry: `#{retry_count}` | Backoff: `{backoff_sec:.1f}s`
Mode: {pause_status}"""
        return text

    def format_feed_ok(self, provider: str, downtime_sec: int) -> str:
        """Format FEED_OK message (once when transitioning from down to ok)."""
        timestamp = self._now_label()
        
        minutes = downtime_sec // 60
        seconds = downtime_sec % 60
        if minutes > 0:
            downtime_str = f"`{minutes}m {seconds}s`"
        else:
            downtime_str = f"`{seconds}s`"
        
        text = f"""**🟢 DATA FEED OK — {provider}**
⏱️ `{timestamp}`
Downtime: {downtime_str}"""
        return text

    def format_daily_report(self, symbol: str, equity_start: float, equity_end: float,
                           pnl_abs: float, pnl_pct: float, num_trades: int, num_buy: int,
                           num_sell: int, win_pct: float, total_fees: float, max_dd: float,
                           position_btc: float, wallet_cash: float, btc_price: float,
                           exposure_pct: float, notes: str = "") -> str:
        """Format DAILY_REPORT message (once per day)."""
        timestamp = self._now_label()
        report_date = timestamp.split(" | ")[1]  # Extract YYYY-MM-DD
        
        text = f"""**📊 DAILY REPORT — PAPER BTC ({report_date})**
Timezone: `Europe/Paris`
Equity: `{equity_start:.2f}` → `{equity_end:.2f}` | PnL: `{pnl_abs:+.2f}` (`{pnl_pct:+.2f}%`)
Trades: `{num_trades}` (B `{num_buy}` / S `{num_sell}`) | Win: `{win_pct:.1f}%` | Fees: `{total_fees:.2f}`
Max DD: `{max_dd:.2f}%` | Position: `{position_btc:.6f} BTC` | Cash: `{wallet_cash:.2f} USDT`
BTC ref: `{btc_price:.2f}` | Exposure: `{exposure_pct:.1f}%`"""
        if notes:
            text += f"\nNotes: {notes}"
        
        return text

    def format_wallet_low(self, cash: float, threshold: float, action: str = "") -> str:
        """Format WALLET_CASH_LOW message (rate limited 1/hour)."""
        timestamp = self._now_label()
        
        text = f"""**🟠 WALLET LOW CASH**
⏱️ `{timestamp}`
Cash: `{cash:.2f} USDT` (seuil `{threshold:.2f}`)
Statut: `WARN`"""
        if action:
            text += f"\nAction: {action}"
        
        return text

    # ============================================================================
    # Legacy methods — delegated to format functions for backward compatibility
    # ============================================================================

    def notify_trade(self, trade: TradeResult, market_price: float, cash: float, btc_qty: float, slippage_rate: float = 0.0002) -> None:
        """Notify about a buy or sell trade."""
        if not trade.executed or trade.side is None:
            return
        
        exec_price = trade.price_exec
        qty = trade.qty_btc
        fee = trade.fee
        equity = cash + (btc_qty * market_price)
        reason = trade.reason or "Signal MA"
        symbol = trade.symbol or "BTCUSDT"
        
        if trade.side.upper() == "BUY":
            text = self.format_trade_buy(
                symbol, market_price, exec_price, qty, fee,
                cash, btc_qty, equity, reason
            )
        else:
            text = self.format_trade_sell(
                symbol, market_price, exec_price, qty, fee,
                cash, btc_qty, equity, reason=reason
            )
        
        self.send_message(text)

    def notify_kill_switch(self, drawdown: float, threshold: float, equity: float) -> None:
        """Notify about kill switch activation."""
        position_btc = 0  # Would need to pass from caller
        text = self.format_kill_switch(drawdown, threshold, equity, position_btc)
        self.send_message(text)

    def notify_feed_down(self, error: str) -> None:
        """Notify about price feed down."""
        text = self.format_feed_down("Binance REST", error, 1, 1.5, False)
        self.send_message(text)

    def notify_feed_recovered(self) -> None:
        """Notify about price feed recovered."""
        text = self.format_feed_ok("Binance REST", 0)
        self.send_message(text)

    def notify_bot_start(self, symbol: str, timeframe: str) -> None:
        """Notify bot startup."""
        text = self.format_startup(symbol, timeframe, "Binance REST")
        self.send_message(text)

    def notify_daily_report(self, report: DailyReport) -> None:
        """Send daily report."""
        text = self.format_daily_report(
            symbol="BTCUSDT",
            equity_start=report.equity_start,
            equity_end=report.equity_end,
            pnl_abs=report.pnl_abs,
            pnl_pct=report.pnl_pct,
            num_trades=report.num_trades,
            num_buy=report.num_buy,
            num_sell=report.num_sell,
            win_pct=report.win_pct,
            total_fees=report.total_fees,
            max_dd=report.max_drawdown,
            position_btc=report.position_btc,
            wallet_cash=report.wallet_cash,
            btc_price=report.btc_price,
            exposure_pct=report.exposure_pct,
            notes=report.notes or ""
        )
        self.send_message(text)

    def notify_alert(self, text: str) -> None:
        """Generic alert."""
        timestamp = self._now_label()
        msg = f"""**📢 ALERT**
⏱️ `{timestamp}`
{text}"""
        self.send_message(msg)
