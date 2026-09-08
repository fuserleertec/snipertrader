-- TimescaleDB schema for Phase 1 OHLCV (Rev. 1.1)
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS ohlcv_bars (
    ts          TIMESTAMPTZ NOT NULL,
    symbol      TEXT        NOT NULL,
    asset_class TEXT        NOT NULL,
    timeframe   TEXT        NOT NULL,
    open        DOUBLE PRECISION NOT NULL,
    high        DOUBLE PRECISION NOT NULL,
    low         DOUBLE PRECISION NOT NULL,
    close       DOUBLE PRECISION NOT NULL,
    volume      DOUBLE PRECISION NOT NULL,
    n_ticks     INTEGER     NOT NULL,
    close_ts    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (ts, symbol, timeframe)
);

SELECT create_hypertable('ohlcv_bars', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS ohlcv_bars_symbol_tf_ts_idx
    ON ohlcv_bars (symbol, timeframe, ts DESC);

CREATE INDEX IF NOT EXISTS ohlcv_bars_asset_ts_idx
    ON ohlcv_bars (asset_class, ts DESC);
