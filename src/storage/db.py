from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.models import Candle, Signal, WalletState


class Database:
    """PostgreSQL-only database wrapper.

    `POSTGRES_DSN` must be set in environment.
    """

    def __init__(self):
        try:
            import psycopg2
            import psycopg2.extras
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError("psycopg2 is required for Postgres support") from exc
        dsn = os.getenv("POSTGRES_DSN", "")
        if not dsn:
            raise RuntimeError("POSTGRES_DSN must be set")

        # keep references for reconnect logic
        self._dsn = dsn
        self._psycopg2 = psycopg2
        self._pg_extras = psycopg2.extras
        self._logger = logging.getLogger("storage.db")

        # establish initial connection
        self._connect()

    def _connect(self) -> None:
        try:
            self.conn = self._psycopg2.connect(self._dsn)
            self.conn.autocommit = False
        except Exception as exc:  # pragma: no cover - operational failures surfaced at runtime
            logging.getLogger("storage.db").exception("Failed to connect to Postgres: %s", exc)
            raise

    def close(self) -> None:
        self.conn.close()

    def init_schema(self, schema_path: Path) -> None:
        sql = schema_path.read_text(encoding="utf-8")
        # Split on semicolon and execute statements individually for psycopg2
        cur = self.conn.cursor()
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            cur.execute(stmt)
            self.conn.commit()
        cur.close()

    def _translate_sql(self, sql: str) -> str:
        # adapt parameter style
        return sql.replace("?", "%s")

    def _execute(self, sql: str, params: tuple | list = (), commit: bool = True):
        try:
            cur = self.conn.cursor(cursor_factory=self._pg_extras.RealDictCursor)
        except (self._psycopg2.InterfaceError, self._psycopg2.OperationalError) as exc:
            # connection was closed by server or lost — try to reconnect once
            self._logger.warning("DB connection lost, attempting reconnect: %s", exc)
            self._connect()
            cur = self.conn.cursor(cursor_factory=self._pg_extras.RealDictCursor)

        cur.execute(self._translate_sql(sql), params)
        if commit:
            self.conn.commit()
        return cur

    @contextmanager
    def transaction(self) -> Iterator[object]:
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN;")

            class _Tx:
                def __init__(self, cur, translate):
                    self._cur = cur
                    self._translate = translate

                def execute(self, sql, params=()):
                    return self._cur.execute(self._translate(sql), params)

            tx = _Tx(cur, self._translate_sql)
            yield tx
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def set_bot_state(self, key: str, value: str) -> None:
        sql = """
        INSERT INTO bot_state(key, value) VALUES(%s, %s)
        ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value
        """
        self._execute(sql, (key, value))

    def get_bot_state(self, key: str) -> str | None:
        cur = self._execute("SELECT value FROM bot_state WHERE key=%s", (key,), commit=False)
        row = cur.fetchone()
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
        sql = """
        INSERT INTO candles(symbol, timeframe, open_time, open, high, low, close, volume, close_time)
        VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, timeframe, open_time) DO NOTHING
        """
        cur = self._execute(sql, (
            candle.symbol,
            candle.timeframe,
            candle.open_time,
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
            candle.close_time,
        ))
        return cur.rowcount > 0

    def insert_signal(self, signal: Signal) -> bool:
        sql = """
        INSERT INTO signals(ts, symbol, timeframe, signal, reason, features_json)
        VALUES(%s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, timeframe, ts) DO NOTHING
        """
        cur = self._execute(sql, (signal.ts, signal.symbol, signal.timeframe, signal.signal, signal.reason, signal.features_json))
        return cur.rowcount > 0

    def get_recent_closes(self, symbol: str, timeframe: str, limit: int) -> list[float]:
        cur = self._execute(
            """
            SELECT close
            FROM candles
            WHERE symbol=%s AND timeframe=%s
            ORDER BY open_time DESC
            LIMIT %s
            """,
            (symbol, timeframe, limit),
            commit=False,
        )
        rows = cur.fetchall()
        return [float(r["close"]) for r in reversed(rows)]

    def get_latest_open_time(self, symbol: str, timeframe: str) -> int | None:
        cur = self._execute(
            """
            SELECT MAX(open_time) AS open_time
            FROM candles
            WHERE symbol=%s AND timeframe=%s
            """,
            (symbol, timeframe),
            commit=False,
        )
        row = cur.fetchone()
        if row is None or row.get("open_time") is None:
            return None
        return int(row["open_time"])

    def trade_exists_for_candle(self, symbol: str, timeframe: str, source_open_time: int) -> bool:
        row = self._execute(
            """
            SELECT 1
            FROM trades
            WHERE symbol=%s AND timeframe=%s AND source_open_time=%s
            LIMIT 1
            """,
            (symbol, timeframe, source_open_time),
            commit=False,
        ).fetchone()
        return row is not None

    def insert_trade(self, payload: dict) -> None:
        sql = """
        INSERT INTO trades(
            trade_id, ts, side, symbol, timeframe, source_open_time, qty_btc,
            price_market, price_exec, fee, cash_after, btc_after, pnl_realized, reason, meta_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        self._execute(
            sql,
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
            commit=False,
        )

    def insert_equity(self, ts: int, cash: float, btc_qty: float, btc_price: float, equity: float, drawdown: float) -> None:
        self._execute(
            """
            INSERT INTO equity(ts, cash, btc_qty, btc_price, equity, drawdown)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (ts, cash, btc_qty, btc_price, equity, drawdown),
            commit=False,
        )

    def get_candles_between(self, symbol: str, timeframe: str, start_open_time: int, end_open_time: int) -> list[Candle]:
        cur = self._execute(
            """
            SELECT symbol, timeframe, open_time, open, high, low, close, volume, close_time
            FROM candles
            WHERE symbol=%s AND timeframe=%s AND open_time BETWEEN %s AND %s
            ORDER BY open_time ASC
            """,
            (symbol, timeframe, start_open_time, end_open_time),
            commit=False,
        )
        rows = cur.fetchall()
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

    def get_equity_between(self, start_ts: int, end_ts: int) -> list[dict]:
        cur = self._execute(
            """
            SELECT ts, cash, btc_qty, btc_price, equity, drawdown
            FROM equity
            WHERE ts BETWEEN %s AND %s
            ORDER BY ts ASC
            """,
            (start_ts, end_ts),
            commit=False,
        )
        return cur.fetchall()

    def get_trades_between(self, start_ts: int, end_ts: int) -> list[dict]:
        cur = self._execute(
            """
            SELECT *
            FROM trades
            WHERE ts BETWEEN %s AND %s
            ORDER BY ts ASC
            """,
            (start_ts, end_ts),
            commit=False,
        )
        return cur.fetchall()
