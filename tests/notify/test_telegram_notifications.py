#!/usr/bin/env python3
"""
Test script to visualize all Telegram notification formats.
Shows how messages look with Paris timezone and readable timestamps.
"""

from datetime import date
import os
from src.models import DailyReport, TradeResult
from src.notify.telegram import TelegramNotifier


def test_all_notifications():
    # Create notifier with Telegram config
    notifier = TelegramNotifier(
        enabled=os.getenv("TELEGRAM_ENABLE", "false").strip().lower() in {"1", "true", "yes", "on"},
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        tz_name=os.getenv("REPORT_TZ", "Europe/Paris"),
    )
    
    if not notifier.enabled:
        print("❌ Telegram is DISABLED. Check your .env: TELEGRAM_ENABLE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
        return
    
    print("✅ Telegram is ENABLED\n")
    
    # Test 1: Bot start notification
    print("=" * 60)
    print("TEST 1: Bot Startup Notification")
    print("=" * 60)
    notifier.notify_bot_start("BTCUSDT", "1m")
    print("✓ Sent\n")
    
    # Test 2: Trade notification (BUY)
    print("=" * 60)
    print("TEST 2: Buy Trade Notification")
    print("=" * 60)
    trade_buy = TradeResult(
        executed=True,
        side="BUY",
        reason="MA10 crossed above MA30",
        trade_id="test-buy-001",
        qty_btc=0.025,
        price_market=69500.0,
        price_exec=69520.5,
        fee=2.50,
    )
    notifier.notify_trade(
        trade_buy,
        market_price=69500.0,
        cash=9750.0,
        btc_qty=0.025,
        slippage_rate=0.0002,
    )
    print("✓ Sent\n")
    
    # Test 3: Trade notification (SELL)
    print("=" * 60)
    print("TEST 3: Sell Trade Notification")
    print("=" * 60)
    trade_sell = TradeResult(
        executed=True,
        side="SELL",
        reason="MA10 crossed below MA30",
        trade_id="test-sell-001",
        qty_btc=0.025,
        price_market=70000.0,
        price_exec=69980.0,
        fee=1.75,
        pnl_realized=12.50,
    )
    notifier.notify_trade(
        trade_sell,
        market_price=70000.0,
        cash=10250.0,
        btc_qty=0.0,
        slippage_rate=0.0002,
    )
    print("✓ Sent\n")
    
    # Test 4: Kill switch notification
    print("=" * 60)
    print("TEST 4: Kill Switch Alert")
    print("=" * 60)
    notifier.notify_kill_switch(
        drawdown=0.152,
        threshold=0.15,
        equity=8500.0,
    )
    print("✓ Sent\n")
    
    # Test 5: Feed down alert
    print("=" * 60)
    print("TEST 5: Feed Down Alert")
    print("=" * 60)
    notifier.notify_feed_down("Connection timeout to Binance API")
    print("✓ Sent\n")
    
    # Test 6: Feed recovered
    print("=" * 60)
    print("TEST 6: Feed Recovered Notification")
    print("=" * 60)
    notifier.notify_feed_recovered()
    print("✓ Sent\n")
    
    # Test 7: Daily report
    print("=" * 60)
    print("TEST 7: Daily Report")
    print("=" * 60)
    report = DailyReport(
        day=str(date.today()),
        equity_start=10000.0,
        equity_end=10425.50,
        pnl_abs=425.50,
        pnl_pct=0.04255,
        trades_count=5,
        buy_count=3,
        sell_count=2,
        winrate=0.75,
        fees_total=8.75,
        max_drawdown=0.042,
        cash_end=5200.0,
        btc_qty_end=0.075,
        btc_price_end=70000.0,
        exposure_pct=0.52,
        notes="feed ok, 5 trades executed",
    )
    notifier.notify_daily_report(report)
    print("✓ Sent\n")
    
    # Test 8: Generic alert
    print("=" * 60)
    print("TEST 8: Generic Alert")
    print("=" * 60)
    notifier.notify_alert("Wallet cash low: 500 USDT remaining")
    print("✓ Sent\n")
    
    print("=" * 60)
    print("🎉 All test notifications sent!")
    print("Check your Telegram chat to see the formatting and readability.")
    print("=" * 60)


if __name__ == "__main__":
    test_all_notifications()
