"""Import candles historiques depuis un CSV ou via l'API REST Binance.

Usage CSV:
    python -m src.scripts.import_candles --csv data/btcusdt_1m.csv

Usage API (fetch):
    python -m src.scripts.import_candles --fetch --days 30

Le CSV doit contenir les colonnes (header) :
    open_time,open,high,low,close,volume,close_time
(open_time et close_time en epoch ms)
"""
from __future__ import annotations

import argparse
import csv
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import load_settings
from src.models import Candle
from src.price_feed.rest_provider import BinanceRestProvider
from src.storage.db import Database


def import_from_csv(db: Database, csv_path: Path, symbol: str, timeframe: str) -> int:
    log = logging.getLogger("import_candles")
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            candle = Candle(
                symbol=symbol,
                timeframe=timeframe,
                open_time=int(row["open_time"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                close_time=int(row["close_time"]),
            )
            if db.insert_candle(candle):
                count += 1
    log.info("Imported %d new candles from %s", count, csv_path)
    return count


def fetch_and_import(db: Database, symbol: str, timeframe: str, days: int) -> int:
    log = logging.getLogger("import_candles")
    provider = BinanceRestProvider()

    end_ms = int(time.time() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

    total = 0
    cursor = start_ms
    while cursor < end_ms:
        url = f"{provider.BASE_URL}/api/v3/klines"
        import requests
        params = {
            "symbol": symbol.upper(),
            "interval": timeframe,
            "startTime": cursor,
            "limit": 1000,
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        if not raw:
            break

        for row in raw:
            candle = Candle(
                symbol=symbol.upper(),
                timeframe=timeframe,
                open_time=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                close_time=int(row[6]),
            )
            if db.insert_candle(candle):
                total += 1
            cursor = candle.close_time + 1

        log.info("Fetched batch, total new candles so far: %d, cursor at %s", total, datetime.fromtimestamp(cursor / 1000, tz=timezone.utc).isoformat())
        time.sleep(0.3)

    log.info("Import done: %d new candles over %d days", total, days)
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

    parser = argparse.ArgumentParser(description="Import candles historiques")
    parser.add_argument("--csv", type=str, help="Chemin vers fichier CSV")
    parser.add_argument("--fetch", action="store_true", help="Fetch depuis Binance REST API")
    parser.add_argument("--days", type=int, default=30, help="Nombre de jours à fetcher (défaut: 30)")
    args = parser.parse_args()

    settings = load_settings()
    schema_path = Path(__file__).resolve().parent.parent / "storage" / "schema.sql"
    db = Database(settings.db_path)
    db.init_schema(schema_path)

    if args.csv:
        import_from_csv(db, Path(args.csv), settings.symbol, settings.timeframe)
    elif args.fetch:
        fetch_and_import(db, settings.symbol, settings.timeframe, args.days)
    else:
        parser.print_help()

    db.close()


if __name__ == "__main__":
    main()
