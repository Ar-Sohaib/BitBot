-- Migration: Add notification tracking columns and table
-- Compatible with both SQLite and PostgreSQL

-- Add notification tracking columns to trades table
ALTER TABLE trades ADD COLUMN notif_sent BOOLEAN DEFAULT FALSE;
ALTER TABLE trades ADD COLUMN notif_sent_at BIGINT DEFAULT 0;

-- Create sent_notifications table for deduplication
CREATE TABLE IF NOT EXISTS sent_notifications (
    event_id TEXT PRIMARY KEY,
    ts BIGINT NOT NULL,
    type TEXT NOT NULL,
    details_json TEXT DEFAULT ''
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_trades_notif_sent ON trades(notif_sent, ts);
CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(symbol, timeframe, open_time);
CREATE INDEX IF NOT EXISTS idx_sent_notifications_ts ON sent_notifications(ts);
