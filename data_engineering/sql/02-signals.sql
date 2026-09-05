-- Signal lifecycle (Quant Phase 1 / Rev. 1.1)
-- Mounted next to 01-init.sql so the shared TimescaleDB has OHLCV + signals.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS signals (
    ts             TIMESTAMPTZ NOT NULL,
    id             TEXT        NOT NULL,
    schema_version TEXT        NOT NULL DEFAULT '1.1',
    symbol         TEXT        NOT NULL,
    asset_class    TEXT        NOT NULL,
    setup_type     TEXT        NOT NULL,
    side           TEXT        NOT NULL,
    confidence     DOUBLE PRECISION,
    ref_vwap       DOUBLE PRECISION,
    ref_session    TEXT,
    entry          DOUBLE PRECISION,
    stop_px        DOUBLE PRECISION,
    target         DOUBLE PRECISION,
    timeframe      TEXT,
    trigger_event_ids TEXT,
    session_type   TEXT,
    position_size  DOUBLE PRECISION,
    status         TEXT        NOT NULL DEFAULT 'ACTIVE',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_ts      TIMESTAMPTZ,
    PRIMARY KEY (id, ts)
);

SELECT create_hypertable('signals', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS signals_symbol_status_ts_idx
    ON signals (symbol, status, ts DESC);

CREATE INDEX IF NOT EXISTS signals_status_ts_idx
    ON signals (status, ts DESC);

CREATE INDEX IF NOT EXISTS signals_id_idx
    ON signals (id);

CREATE TABLE IF NOT EXISTS account_daily (
    account_id   TEXT        NOT NULL,
    day          DATE        NOT NULL,
    equity       DOUBLE PRECISION NOT NULL,
    realized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (account_id, day)
);
