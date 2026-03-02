from __future__ import annotations

import json
import logging
import threading
import uuid

from src.config import Settings
from src.models import Candle, Signal, TradeResult, WalletState
from src.broker.risk import compute_drawdown, compute_equity
from src.storage.db import Database


class PaperBroker:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self._lock = threading.Lock()
        self.log = logging.getLogger("paper_broker")
        self.wallet = self.load_state()

    def load_state(self) -> WalletState:
        state = self.db.load_wallet_state()
        if state is not None:
            return state
        initial = WalletState(
            cash=self.settings.starting_cash,
            btc_qty=0.0,
            avg_entry_price=0.0,
            fees_paid_total=0.0,
            is_blocked=False,
            peak_equity=self.settings.starting_cash,
        )
        self.db.save_wallet_state(initial)
        return initial

    def get_state(self) -> WalletState:
        return WalletState(**self.wallet.__dict__)

    def _persist_wallet_state(self, conn, wallet: WalletState) -> None:
        payload = json.dumps(
            {
                "cash": wallet.cash,
                "btc_qty": wallet.btc_qty,
                "avg_entry_price": wallet.avg_entry_price,
                "fees_paid_total": wallet.fees_paid_total,
                "is_blocked": wallet.is_blocked,
                "peak_equity": wallet.peak_equity,
            }
        )
        conn.execute(
            """
            INSERT INTO bot_state(key, value) VALUES('wallet_state', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (payload,),
        )

    def _persist_last_processed(self, conn, candle_open_time: int) -> None:
        conn.execute(
            """
            INSERT INTO bot_state(key, value) VALUES('last_processed_open_time', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (str(candle_open_time),),
        )

    def _snapshot_equity_in_txn(self, conn, ts: int, price: float) -> tuple[float, float]:
        equity = compute_equity(self.wallet.cash, self.wallet.btc_qty, price)
        self.wallet.peak_equity = max(self.wallet.peak_equity, equity)
        drawdown = compute_drawdown(equity, self.wallet.peak_equity)
        conn.execute(
            """
            INSERT INTO equity(ts, cash, btc_qty, btc_price, equity, drawdown)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (ts, self.wallet.cash, self.wallet.btc_qty, price, equity, drawdown),
        )
        return equity, drawdown

    def apply_daily_topup(self, ts: int, price: float) -> float:
        """Apply configured daily top-up to wallet.cash and persist state.

        Returns the amount added (0 if disabled or amount 0).
        """
        amount = 0.0
        if not self.settings.daily_topup_enabled:
            return amount

        amount = float(self.settings.daily_topup_amount)
        if amount <= 0:
            return 0.0

        with self.db.transaction() as conn:
            # increase cash
            self.wallet.cash += amount
            # update peak equity potentially
            equity = compute_equity(self.wallet.cash, self.wallet.btc_qty, price)
            self.wallet.peak_equity = max(self.wallet.peak_equity, equity)
            # persist wallet_state and snapshot
            self._persist_wallet_state(conn, self.wallet)
            self._snapshot_equity_in_txn(conn, ts, price)
        self.log.info("Daily top-up applied amount=%.2f new_cash=%.2f", amount, self.wallet.cash)
        return amount

    def _apply_kill_switch(self, drawdown: float) -> None:
        if drawdown > self.settings.kill_switch_drawdown_pct:
            self.wallet.is_blocked = True

    def execute_signal(self, signal: Signal, candle: Candle) -> TradeResult:
        with self._lock:
            if self.db.trade_exists_for_candle(candle.symbol, candle.timeframe, candle.open_time):
                return TradeResult(
                    executed=False,
                    side=None,
                    reason="Candle already processed (idempotence)",
                )

            if self.wallet.is_blocked and signal.signal in {"BUY", "SELL"}:
                with self.db.transaction() as conn:
                    _, drawdown = self._snapshot_equity_in_txn(conn, candle.close_time, candle.close)
                    self._persist_last_processed(conn, candle.open_time)
                    self._persist_wallet_state(conn, self.wallet)
                return TradeResult(executed=False, side=None, reason=f"Trading blocked (DD={drawdown:.2%})")

            if signal.signal == "HOLD":
                with self.db.transaction() as conn:
                    _, drawdown = self._snapshot_equity_in_txn(conn, candle.close_time, candle.close)
                    self._apply_kill_switch(drawdown)
                    self._persist_last_processed(conn, candle.open_time)
                    self._persist_wallet_state(conn, self.wallet)
                return TradeResult(executed=False, side=None, reason=signal.reason)

            if signal.signal == "BUY":
                return self._execute_buy(signal, candle)
            if signal.signal == "SELL":
                return self._execute_sell(signal, candle)

            return TradeResult(executed=False, side=None, reason="Unknown signal")

    def _execute_buy(self, signal: Signal, candle: Candle) -> TradeResult:
        budget = self.wallet.cash * self.settings.max_position_pct
        if budget < self.settings.min_order_notional:
            with self.db.transaction() as conn:
                self._snapshot_equity_in_txn(conn, candle.close_time, candle.close)
                self._persist_last_processed(conn, candle.open_time)
                self._persist_wallet_state(conn, self.wallet)
            return TradeResult(executed=False, side=None, reason="Notional too low for BUY")

        price_market = candle.close
        price_exec = price_market * (1 + self.settings.slippage_rate)
        fee = budget * self.settings.fee_rate
        qty = (budget - fee) / price_exec

        if qty <= 0:
            return TradeResult(executed=False, side=None, reason="BUY qty <= 0")

        cash_before = self.wallet.cash
        btc_before = self.wallet.btc_qty

        self.wallet.cash -= budget
        self.wallet.btc_qty += qty
        self.wallet.fees_paid_total += fee

        if self.wallet.btc_qty > 0:
            self.wallet.avg_entry_price = (
                (btc_before * self.wallet.avg_entry_price) + (qty * price_exec)
            ) / self.wallet.btc_qty

        trade_id = str(uuid.uuid4())
        with self.db.transaction() as conn:
            self.db.insert_trade(
                {
                    "trade_id": trade_id,
                    "ts": candle.close_time,
                    "side": "BUY",
                    "symbol": candle.symbol,
                    "timeframe": candle.timeframe,
                    "source_open_time": candle.open_time,
                    "qty_btc": qty,
                    "price_market": price_market,
                    "price_exec": price_exec,
                    "fee": fee,
                    "cash_after": self.wallet.cash,
                    "btc_after": self.wallet.btc_qty,
                    "pnl_realized": 0.0,
                    "reason": signal.reason,
                    "meta_json": signal.features_json,
                }
            )
            _, drawdown = self._snapshot_equity_in_txn(conn, candle.close_time, candle.close)
            self._apply_kill_switch(drawdown)
            self._persist_last_processed(conn, candle.open_time)
            self._persist_wallet_state(conn, self.wallet)

        self.log.info(
            "BUY executed trade_id=%s market=%.2f exec=%.2f qty=%.8f fee=%.4f cash_before=%.2f cash_after=%.2f",
            trade_id,
            price_market,
            price_exec,
            qty,
            fee,
            cash_before,
            self.wallet.cash,
        )

        return TradeResult(
            executed=True,
            side="BUY",
            reason=signal.reason,
            trade_id=trade_id,
            qty_btc=qty,
            price_market=price_market,
            price_exec=price_exec,
            fee=fee,
        )

    def _execute_sell(self, signal: Signal, candle: Candle) -> TradeResult:
        qty = self.wallet.btc_qty
        if qty <= 0:
            with self.db.transaction() as conn:
                self._snapshot_equity_in_txn(conn, candle.close_time, candle.close)
                self._persist_last_processed(conn, candle.open_time)
                self._persist_wallet_state(conn, self.wallet)
            return TradeResult(executed=False, side=None, reason="No BTC to SELL")

        price_market = candle.close
        price_exec = price_market * (1 - self.settings.slippage_rate)

        notional = qty * price_exec
        fee = notional * self.settings.fee_rate
        pnl_realized = (price_exec - self.wallet.avg_entry_price) * qty - fee

        self.wallet.cash += notional - fee
        self.wallet.btc_qty = 0.0
        self.wallet.avg_entry_price = 0.0
        self.wallet.fees_paid_total += fee

        trade_id = str(uuid.uuid4())
        with self.db.transaction() as conn:
            self.db.insert_trade(
                {
                    "trade_id": trade_id,
                    "ts": candle.close_time,
                    "side": "SELL",
                    "symbol": candle.symbol,
                    "timeframe": candle.timeframe,
                    "source_open_time": candle.open_time,
                    "qty_btc": qty,
                    "price_market": price_market,
                    "price_exec": price_exec,
                    "fee": fee,
                    "cash_after": self.wallet.cash,
                    "btc_after": self.wallet.btc_qty,
                    "pnl_realized": pnl_realized,
                    "reason": signal.reason,
                    "meta_json": signal.features_json,
                }
            )
            _, drawdown = self._snapshot_equity_in_txn(conn, candle.close_time, candle.close)
            self._apply_kill_switch(drawdown)
            self._persist_last_processed(conn, candle.open_time)
            self._persist_wallet_state(conn, self.wallet)

        self.log.info(
            "SELL executed trade_id=%s market=%.2f exec=%.2f qty=%.8f fee=%.4f pnl_realized=%.4f",
            trade_id,
            price_market,
            price_exec,
            qty,
            fee,
            pnl_realized,
        )

        return TradeResult(
            executed=True,
            side="SELL",
            reason=signal.reason,
            trade_id=trade_id,
            qty_btc=qty,
            price_market=price_market,
            price_exec=price_exec,
            fee=fee,
            pnl_realized=pnl_realized,
        )
