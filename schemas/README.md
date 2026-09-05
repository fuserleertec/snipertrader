# Kafka / JSON schemas (Rev. 1.1)

Canonical message contracts for the Phase 1 streaming pipeline.
The Python package `sniper_data` serializes these shapes onto the topics
listed below. JSON Schema is draft 2020-12.

| Topic | Schema file | Producer | Consumers |
|---|---|---|---|
| `raw_ticks` | [`raw_tick.schema.json`](raw_tick.schema.json) | Exchange adapters / mock feed | OHLCV, session tracker, VWAP |
| `ohlcv_bars` | [`ohlcv_bar.schema.json`](ohlcv_bar.schema.json) | OHLCV aggregator | Timescale writer, research |
| `session_levels` | [`session_levels.schema.json`](session_levels.schema.json) | Session tracker | Redis, Quant API |
| `vwap_values` | [`vwap_values.schema.json`](vwap_values.schema.json) | VWAP engine | Redis, WebSocket, Quant API |
| `sweep_events` | [`sweep_event.schema.json`](sweep_event.schema.json) | Pattern detectors (Phase 2 stub) | Redis `sweep:{symbol}:{id}` |
| `fvg_zones` | [`fvg_zone.schema.json`](fvg_zone.schema.json) | Pattern detectors (Phase 2 stub) | Redis `fvg:{symbol}:{id}` |
| `setup_signals` | [`setup_signal.schema.json`](setup_signal.schema.json) | Signal engine (after Risk Pre-Filter) | Downstream ML / UI / `quant/` lifecycle |

HTTP contracts used by Quant (`POST /risk/validate`) — not Kafka topics:

| HTTP | Schema file | Notes |
|---|---|---|
| `POST /risk/validate` body | [`risk_validate_request.schema.json`](risk_validate_request.schema.json) | Candidate — **omit `id`**. Required risk fields: `entry`, `stop`, `target`, `timeframe` ∈ {1m,5m,15m}, `trigger_event_ids` |
| `POST /risk/validate` response | [`risk_validate_response.schema.json`](risk_validate_response.schema.json) | `{approved, reason, adjusted_position_size}` |

`setup_type` (locked, Phase 1): `sweep_reclaim` · `fvg_entry` · `mss_break` · `order_block` · `sweep_mss` · `ob_fvg`.

`setup_signal.schema.json` is additive in Rev. 1.1: optional `entry`, `stop`, `target`, `timeframe`, `trigger_event_ids`, `session_type`, `position_size`, `status`. Kafka publish still **requires** `id`. ML assigns `id` only after the Risk Pre-Filter approves. See [`quant/README.md`](../quant/README.md).

Redis key map (real-time state, not Kafka):

| Key | TTL | Notes |
|---|---|---|
| `session:{symbol}:{session_type}` | none (live book) | OHLC for the current window |
| `vwap:{symbol}:{anchor_type}` | none (live book) | VWAP + σ bands |
| `fvg:{symbol}:{id}` | **≤ 48h (required)** | Fair-value gap zone |
| `sweep:{symbol}:{id}` | **≤ 48h (required)** | Liquidity sweep zone |

`anchor_type` ∈ `session` · `weekly` · `rolling`.
`session_type` ∈ `asia` · `london` · `ny_am` · `ny_pm` · `rth` · `eth` · `globex`.
