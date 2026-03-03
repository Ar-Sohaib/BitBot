from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    app_env: str
    log_level: str

    symbol: str
    timeframe: str

    starting_cash: float
    fee_rate: float
    slippage_rate: float
    max_position_pct: float
    min_order_notional: float
    kill_switch_drawdown_pct: float
    ma_fast: int
    ma_slow: int

    db_path: Path
    poll_seconds: int
    price_source: str
    db_type: str = "Postgres"  # "sqlite" or "postgres"
    postgres_dsn: str = ""

    telegram_enable: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    report_tz: str = "Europe/Paris"

    # Daily top-up (add amount to cash at start of each trading day)
    daily_topup_enabled: bool = True
    daily_topup_amount: float = 5.0



def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    load_dotenv(override=False)

    db_path = Path(os.getenv("DB_PATH", "data/paper.db")).expanduser()

    return Settings(
        app_env=os.getenv("APP_ENV", "dev"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        symbol=os.getenv("SYMBOL", "BTCUSDT").upper(),
        timeframe=os.getenv("TIMEFRAME", "1m"),
        starting_cash=float(os.getenv("STARTING_CASH", "10000")),
        fee_rate=float(os.getenv("FEE_RATE", "0.001")),
        slippage_rate=float(os.getenv("SLIPPAGE_RATE", "0.0002")),
        max_position_pct=float(os.getenv("MAX_POSITION_PCT", "0.2")),
        min_order_notional=float(os.getenv("MIN_ORDER_NOTIONAL", "10")),
        kill_switch_drawdown_pct=float(os.getenv("KILL_SWITCH_DRAWDOWN_PCT", "0.15")),
        ma_fast=int(os.getenv("MA_FAST", "10")),
        ma_slow=int(os.getenv("MA_SLOW", "30")),
        db_path=db_path,
        db_type=os.getenv("DB_TYPE", "sqlite").lower(),
        postgres_dsn=os.getenv("POSTGRES_DSN", ""),
        poll_seconds=int(os.getenv("POLL_SECONDS", "15")),
        price_source=os.getenv("PRICE_SOURCE", "binance"),
        telegram_enable=_env_bool("TELEGRAM_ENABLE", False),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        report_tz=os.getenv("REPORT_TZ", "Europe/Paris"),
        daily_topup_enabled=_env_bool("DAILY_TOPUP_ENABLED", False),
        daily_topup_amount=float(os.getenv("DAILY_TOPUP_AMOUNT", "0")),
    )
