from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.models import Candle, Signal, WalletState


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")

    def close(self) -> None:
        self.conn.close()

    def init_schema(self, schema_path: Path) -> None:
        sql = schema_path.read_text(encoding="utf-8")
        self.conn.executescript(sql)
        self.conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def set_bot_state(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO bot_state(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )
        self.conn.commit()

    def get_bot_state(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM bot_state WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def save_wallet_state(self, wallet: WalletState) -> None:
        payload = {
            "cash": wallet.cash,
            "btc_qty": wallet.btc_qty,
            "avg_entry_price": wallet.avg_entry_price,
            "fees_paid_total": wallet.fees_paid_total,
            "is_blocked": wallet.is_blocked,
            "peak_equity": wallet.peak_equity,
        }
        self.set_bot_state("wallet_state", json.dumps(payload))

    def load_wallet_state(self) -> WalletState | None:
        raw = self.get_bot_state("wallet_state")
        if not raw:
            return None
        data = json.loads(raw)
        return WalletState(
            cash=float(data["cash"]),
            btc_qty=float(data["btc_qty"]),
            avg_entry_price=float(data["avg_entry_price"]),
            fees_paid_total=float(data["fees_paid_total"]),
            is_blocked=bool(data["is_blocked"]),
            peak_equity=float(data.get("peak_equity", data["cash"])),
        )

    def insert_candle(self, candle: Candle) -> bool:
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO candles(symbol, timeframe, open_time, open, high, low, close, volume, close_time)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candle.symbol,
                candle.timeframe,
                candle.open_time,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.close_time,
            ),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def insert_signal(self, signal: Signal) -> bool:
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO signals(ts, symbol, timeframe, signal, reason, features_json)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                signal.ts,
                signal.symbol,
                signal.timeframe,
                signal.signal,
                signal.reason,
                signal.features_json,
            ),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_recent_closes(self, symbol: str, timeframe: str, limit: int) -> list[float]:
        rows = self.conn.execute(
            """
            SELECT close
            FROM candles
            WHERE symbol=? AND timeframe=?
            ORDER BY open_time DESC
            LIMIT ?
            """,
            (symbol, timeframe, limit),
        ).fetchall()
        return [float(r["close"]) for r in reversed(rows)]

    def get_latest_open_time(self, symbol: str, timeframe: str) -> int | None:
        row = self.conn.execute(
            """
            SELECT MAX(open_time) AS open_time
            FROM candles
            WHERE symbol=? AND timeframe=?
            """,
            (symbol, timeframe),
        ).fetchone()
        if row is None or row["open_time"] is None:
            return None
        return int(row["open_time"])

    def trade_exists_for_candle(self, symbol: str, timeframe: str, source_open_time: int) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM trades
            WHERE symbol=? AND timeframe=? AND source_open_time=?
            LIMIT 1
            """,
            (symbol, timeframe, source_open_time),
        ).fetchone()
        return row is not None

    def insert_trade(self, payload: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO trades(
                trade_id, ts, side, symbol, timeframe, source_open_time, qty_btc,
                price_market, price_exec, fee, cash_after, btc_after, pnl_realized, reason, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["trade_id"],
                payload["ts"],
                payload["side"],
                payload["symbol"],
                payload["timeframe"],
                payload["source_open_time"],
                payload["qty_btc"],
                payload["price_market"],
                payload["price_exec"],
                payload["fee"],
                payload["cash_after"],
                payload["btc_after"],
                payload["pnl_realized"],
                payload.get("reason", ""),
                payload.get("meta_json", ""),
            ),
        )

    def insert_equity(self, ts: int, cash: float, btc_qty: float, btc_price: float, equity: float, drawdown: float) -> None:
        self.conn.execute(
            """
            INSERT INTO equity(ts, cash, btc_qty, btc_price, equity, drawdown)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ts, cash, btc_qty, btc_price, equity, drawdown),
        )

    def get_candles_between(self, symbol: str, timeframe: str, start_open_time: int, end_open_time: int) -> list[Candle]:
        rows = self.conn.execute(
            """
            SELECT symbol, timeframe, open_time, open, high, low, close, volume, close_time
            FROM candles
            WHERE symbol=? AND timeframe=? AND open_time BETWEEN ? AND ?
            ORDER BY open_time ASC
            """,
            (symbol, timeframe, start_open_time, end_open_time),
        ).fetchall()
        return [
            Candle(
                symbol=str(r["symbol"]),
                timeframe=str(r["timeframe"]),
                open_time=int(r["open_time"]),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=float(r["volume"]),
                close_time=int(r["close_time"]),
            )
            for r in rows
        ]

    def get_equity_between(self, start_ts: int, end_ts: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT ts, cash, btc_qty, btc_price, equity, drawdown
            FROM equity
            WHERE ts BETWEEN ? AND ?
            ORDER BY ts ASC
            """,
            (start_ts, end_ts),
        ).fetchall()

    def get_trades_between(self, start_ts: int, end_ts: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT *
            FROM trades
            WHERE ts BETWEEN ? AND ?
            ORDER BY ts ASC
            """,
            (start_ts, end_ts),
        ).fetchall()
