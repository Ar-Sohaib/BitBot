CREATE TABLE IF NOT EXISTS candles (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open_time INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    close_time INTEGER NOT NULL,
    UNIQUE(symbol, timeframe, open_time)
);

CREATE TABLE IF NOT EXISTS signals (
    ts INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    signal TEXT NOT NULL,
    reason TEXT NOT NULL,
    features_json TEXT DEFAULT '',
    UNIQUE(symbol, timeframe, ts)
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    ts INTEGER NOT NULL,
    side TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    source_open_time INTEGER NOT NULL,
    qty_btc REAL NOT NULL,
    price_market REAL NOT NULL,
    price_exec REAL NOT NULL,
    fee REAL NOT NULL,
    cash_after REAL NOT NULL,
    btc_after REAL NOT NULL,
    pnl_realized REAL NOT NULL DEFAULT 0,
    reason TEXT DEFAULT '',
    meta_json TEXT DEFAULT '',
    UNIQUE(symbol, timeframe, source_open_time)
);

CREATE TABLE IF NOT EXISTS equity (
    ts INTEGER NOT NULL,
    cash REAL NOT NULL,
    btc_qty REAL NOT NULL,
    btc_price REAL NOT NULL,
    equity REAL NOT NULL,
    drawdown REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
