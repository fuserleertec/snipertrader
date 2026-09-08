# Kafka / JSON schemas (Rev. 1.1)

Canonical message contracts for the Phase 1 streaming pipeline.
The Python package `sniper_data` serializes these shapes onto the topics
listed below. JSON Schema is draft 2020-12. `schema_version` is `"1.1"`;
`additionalProperties` is `false`. New ML fields are optional unless listed
as required on a **new** schema.

| Topic | Schema file | Producer | Consumers |
|---|---|---|---|
| `raw_ticks` | [`raw_tick.schema.json`](raw_tick.schema.json) | Exchange adapters / mock feed | OHLCV, session tracker, VWAP |
| `ohlcv_bars` | [`ohlcv_bar.schema.json`](ohlcv_bar.schema.json) | OHLCV aggregator | Timescale writer, research |
| `session_levels` | [`session_levels.schema.json`](session_levels.schema.json) | Session tracker | Redis, Quant API |
| `vwap_values` | [`vwap_values.schema.json`](vwap_values.schema.json) | VWAP engine | Redis, WebSocket, Quant API |
| `sweep_events` | [`sweep_event.schema.json`](sweep_event.schema.json) | Pattern detectors (Phase 2 stub) | Redis `sweep:{symbol}:{id}` |
| `fvg_zones` | [`fvg_zone.schema.json`](fvg_zone.schema.json) | Pattern detectors (Phase 2 stub) | Redis `fvg:{symbol}:{id}` |
| `mss_events` | [`mss_event.schema.json`](mss_event.schema.json) | Pattern detectors (Phase 2 stub) | Redis `mss:{symbol}:{id}` |
| `order_block_zones` | [`order_block.schema.json`](order_block.schema.json) | Pattern detectors (Phase 2 stub) | Redis `ob:{symbol}:{id}` |
| `setup_signals` | [`setup_signal.schema.json`](setup_signal.schema.json) | Signal engine (Phase 2 stub) | Downstream ML / UI |

## Delta / aggressor (ML Researchers)

- `raw_tick.aggressor`: optional `"buy"` \| `"sell"`. Signed trade volume =
  `+volume` if buy, `-volume` if sell. If `aggressor` is missing, classify vs
  mid `((bid+ask)/2)`: `price >= mid` → buy, else sell. Optional
  `is_buyer_maker` (Binance `m`): `true` ⇒ buyer was maker ⇒ aggressor is sell.
- `ohlcv_bar.buy_volume` / `sell_volume`: optional classified sums. Consumers
  compute `delta = buy_volume - sell_volume` — **no `delta` field** on the bar.
  When both are set, `buy_volume + sell_volume` should approximately equal
  `volume`.

## Sweep semantics

`side=sell` = sell-side liquidity (session **high** swept).
`side=buy` = buy-side liquidity (session **low** swept).
Use `side` + `swept_level` only — no `direction` / `sweep_level` aliases.

Redis key map (real-time state, not Kafka):

| Key | TTL | Notes |
|---|---|---|
| `session:{symbol}:{session_type}` | none (live book) | OHLC for the current window |
| `vwap:{symbol}:{anchor_type}` | none (live book) | VWAP + σ bands |
| `fvg:{symbol}:{id}` | **≤ 48h (required)** | Fair-value gap zone |
| `sweep:{symbol}:{id}` | **≤ 48h (required)** | Liquidity sweep zone |
| `mss:{symbol}:{id}` | **≤ 48h (required)** | Market-structure shift |
| `ob:{symbol}:{id}` | **≤ 48h (required)** | Order-block zone |

`anchor_type` ∈ `session` · `weekly` · `rolling`.
`session_type` ∈ `asia` · `london` · `ny_am` · `ny_pm` · `rth` · `eth` · `globex`.
