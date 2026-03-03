#!/usr/bin/env python3
"""
Exemple d'utilisation du système de notifications refactorisé.
Démontre comment utiliser TelegramNotifier et TelegramDispatcher.
"""

from src.storage.db import Database
from src.notify.telegram import TelegramNotifier
from src.notify.dispatcher import TelegramDispatcher


def example_usage():
    """Exemple d'intégration du dispatcher dans main_live.py."""

    # Initialisation
    from pathlib import Path
    db = Database()
    
    # Initialize schema
    schema_path = Path(__file__).resolve().parent.parent / "src" / "storage" / "schema.sql"
    db.init_schema(schema_path)
    notifier = TelegramNotifier(
        enabled=True,
        bot_token="YOUR_TOKEN_HERE",
        chat_id="YOUR_CHAT_ID_HERE"
    )
    dispatcher = TelegramDispatcher(db=db, tz_name="Europe/Paris")
    
    # =========================================================================
    # 1. STARTUP — Envoyé max 1 fois / 6h
    # =========================================================================
    print("1. Vérifier et envoyer startup...")
    if dispatcher.should_send_startup():
        startup_text = notifier.format_startup(
            symbol="BTCUSDT",
            timeframe="1m",
            source="Binance REST"
        )
        # notifier.send_message(startup_text)  # Décommentez pour envoyer
        dispatcher.mark_startup_sent()
        print("✓ Startup notification would be sent")
    else:
        print("✓ Startup rate limit active, skipped")
    
    # =========================================================================
    # 2. TRADE — Idempotent via trade_id
    # =========================================================================
    print("\n2. Envoyer notification de trade...")
    trade_id = "trade_12345"
    if dispatcher.should_send_trade(trade_id):
        trade_text = notifier.format_trade_buy(
            symbol="BTCUSDT",
            market_price=42500.0,
            exec_price=42510.0,
            qty=0.001,
            fee=1.25,
            wallet_cash=9998.75,
            wallet_btc=0.001,
            equity=10253.75,
            reason="MA10 > MA30"
        )
        # notifier.send_message(trade_text)  # Décommentez pour envoyer
        dispatcher.mark_trade_sent(trade_id)
        print("✓ Trade notification would be sent")
    else:
        print("✓ Trade already notified, skipped")
    
    # =========================================================================
    # 3. FEED DOWN/OK — Transition-based, pas d'inondation
    # =========================================================================
    print("\n3. Gérer feed prix down/ok...")
    
    # Première erreur
    if dispatcher.should_send_feed_down():
        feed_down_text = notifier.format_feed_down(
            provider="Binance REST",
            error_msg="Connection timeout (30s)",
            retry_count=1,
            backoff_sec=1.5,
            trading_paused=False
        )
        # notifier.send_message(feed_down_text)  # Décommentez pour envoyer
        dispatcher.mark_feed_down()
        print("✓ Feed DOWN notification would be sent")
    else:
        print("✓ Feed already DOWN, skipped")
    
    # Correction du feed (downtime calculé)
    if dispatcher.should_send_feed_ok():
        downtime = dispatcher.get_feed_downtime_seconds()
        feed_ok_text = notifier.format_feed_ok(
            provider="Binance REST",
            downtime_sec=downtime
        )
        # notifier.send_message(feed_ok_text)  # Décommentez pour envoyer
        dispatcher.mark_feed_ok()
        print(f"✓ Feed OK notification would be sent (downtime: {downtime}s)")
    else:
        print("✓ Feed not DOWN, skipped OK")
    
    # =========================================================================
    # 4. WALLET LOW — Rate limited 1/h, tant que cash < seuil
    # =========================================================================
    print("\n4. Envoyer alerte cash faible...")
    if dispatcher.should_send_wallet_low():
        wallet_low_text = notifier.format_wallet_low(
            cash=500.0,
            threshold=1000.0,
            action="Reduce order size by 50%"
        )
        # notifier.send_message(wallet_low_text)  # Décommentez pour envoyer
        dispatcher.mark_wallet_low_sent()
        print("✓ Wallet LOW notification would be sent")
    else:
        print("✓ Wallet LOW rate limit active, skipped")
    
    # =========================================================================
    # 5. DAILY REPORT — 1 fois / jour
    # =========================================================================
    print("\n5. Envoyer daily report...")
    from datetime import datetime
    today = datetime.now().date().isoformat()
    
    if dispatcher.should_send_daily_report(today):
        daily_text = notifier.format_daily_report(
            symbol="BTCUSDT",
            equity_start=10000.0,
            equity_end=10244.67,
            pnl_abs=244.67,
            pnl_pct=2.45,
            num_trades=5,
            num_buy=2,
            num_sell=3,
            win_pct=80.0,
            total_fees=6.89,
            max_dd=8.5,
            position_btc=0.001,
            wallet_cash=10244.67,
            btc_price=42500.0,
            exposure_pct=17.2
        )
        # notifier.send_message(daily_text)  # Décommentez pour envoyer
        dispatcher.mark_daily_report_sent(today)
        print("✓ Daily REPORT notification would be sent")
    else:
        print("✓ Daily REPORT already sent today, skipped")
    
    # =========================================================================
    # 6. KILL SWITCH — Sans rate limit (une fois par incident)
    # =========================================================================
    print("\n6. Envoyer alerte kill switch...")
    kill_text = notifier.format_kill_switch(
        drawdown=15.75,
        threshold=10.0,
        equity=9754.32,
        position_btc=0.0
    )
    # notifier.send_message(kill_text)  # Décommentez pour envoyer
    print("✓ Kill switch notification would be sent")
    
    print("\n" + "=" * 70)
    print("Exemple complété. Décommentez les .send_message() pour envoyer.")
    print("=" * 70)


if __name__ == "__main__":
    example_usage()
