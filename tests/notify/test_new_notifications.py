#!/usr/bin/env python3
"""
Test script to demonstrate all 8 notification types with new formats.
Generates the Telegram Markdown text for each event type without sending.
"""

from src.notify.telegram import TelegramNotifier


def test_all_notifications():
    """Generate and print all 8 notification formats."""
    
    # Create a notifier (enabled=False so it doesn't actually send)
    notifier = TelegramNotifier(
        enabled=False,
        bot_token="dummy_token",
        chat_id="dummy_chat_id"
    )
    
    print("=" * 80)
    print("TEST: All 8 Notification Formats (New Templates)")
    print("=" * 80)
    
    # 1. STARTUP
    print("\n1️⃣  STARTUP MESSAGE:")
    print("-" * 80)
    startup_msg = notifier.format_startup(
        symbol="BTCUSDT",
        timeframe="1m",
        source="Binance REST",
        version="1.0.0",
        db_name="paper.db"
    )
    print(startup_msg)
    
    # 2. TRADE BUY
    print("\n2️⃣  TRADE BUY MESSAGE:")
    print("-" * 80)
    buy_msg = notifier.format_trade_buy(
        symbol="BTCUSDT",
        market_price=42500.50,
        exec_price=42510.75,
        qty=0.001234,
        fee=1.25,
        wallet_cash=9998.75,
        wallet_btc=0.005678,
        equity=10239.12,
        reason="MA10/MA30 crossover"
    )
    print(buy_msg)
    
    # 3. TRADE SELL
    print("\n3️⃣  TRADE SELL MESSAGE:")
    print("-" * 80)
    sell_msg = notifier.format_trade_sell(
        symbol="BTCUSDT",
        market_price=43200.25,
        exec_price=43190.00,
        qty=0.001234,
        fee=1.35,
        wallet_cash=10053.89,
        wallet_btc=0.004444,
        equity=10244.67,
        pnl_trade_abs=53.12,
        pnl_trade_pct=3.95,
        pnl_day_abs=53.12,
        reason="MA10 < MA30"
    )
    print(sell_msg)
    
    # 4. KILL SWITCH
    print("\n4️⃣  KILL SWITCH MESSAGE:")
    print("-" * 80)
    kill_msg = notifier.format_kill_switch(
        drawdown=15.75,
        threshold=10.0,
        equity=9754.32,
        position_btc=0.0
    )
    print(kill_msg)
    
    # 5. FEED DOWN
    print("\n5️⃣  FEED DOWN MESSAGE:")
    print("-" * 80)
    feed_down_msg = notifier.format_feed_down(
        provider="Binance REST",
        error_msg="Connection timeout (30s)",
        retry_count=1,
        backoff_sec=1.5,
        trading_paused=False
    )
    print(feed_down_msg)
    
    # 6. FEED OK
    print("\n6️⃣  FEED OK MESSAGE:")
    print("-" * 80)
    feed_ok_msg = notifier.format_feed_ok(
        provider="Binance REST",
        downtime_sec=47
    )
    print(feed_ok_msg)
    
    # 7. DAILY REPORT
    print("\n7️⃣  DAILY REPORT MESSAGE:")
    print("-" * 80)
    daily_msg = notifier.format_daily_report(
        symbol="BTCUSDT",
        equity_start=10000.00,
        equity_end=10244.67,
        pnl_abs=244.67,
        pnl_pct=2.45,
        num_trades=5,
        num_buy=2,
        num_sell=3,
        win_pct=80.0,
        total_fees=6.89,
        max_dd=8.5,
        position_btc=0.004444,
        wallet_cash=10053.89,
        btc_price=43200.25,
        exposure_pct=17.2,
        notes="Strong uptrend, good entry/exit timing"
    )
    print(daily_msg)
    
    # 8. WALLET LOW CASH
    print("\n8️⃣  WALLET LOW CASH MESSAGE:")
    print("-" * 80)
    wallet_low_msg = notifier.format_wallet_low(
        cash=500.50,
        threshold=1000.0,
        action="Reduce order size by 50%"
    )
    print(wallet_low_msg)
    
    print("\n" + "=" * 80)
    print("All 8 notification types generated successfully!")
    print("=" * 80)


if __name__ == "__main__":
    test_all_notifications()
