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
| `sweep_events` | [`sweep_event.schema.json`](sweep_event.schema.json) | Sweep detector (`sniper_data.pattern_detection`) | Redis `sweep:{symbol}:{id}`, MSS detector |
| `fvg_zones` | [`fvg_zone.schema.json`](fvg_zone.schema.json) | FVG detector | Redis `fvg:{symbol}:{id}` |
| `mss_events` | [`mss_event.schema.json`](mss_event.schema.json) | MSS detector | Redis `mss:{symbol}:{id}` |
| `order_block_zones` | [`order_block.schema.json`](order_block.schema.json) | Order-block detector | Redis `ob:{symbol}:{id}` |
| `setup_signals` | [`setup_signal.schema.json`](setup_signal.schema.json) | ML setup detectors (after Quant risk approval) | Quant / frontend |
| `kill_zone_events` | [`kill_zone_event.schema.json`](kill_zone_event.schema.json) | Kill-zone timer (Phase 2) | Redis `kill_zone:{symbol}`, Frontend / ML |
| `anchor_events` | (inbound `AnchorRegistration` JSON) | ML swing/MSS + HTTP `/v1/anchors` | Anchored VWAP engine |

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

## Phase 2 wire contracts

Phase 2 Redis / Kafka payloads **do not include `schema_version`**. Field names
match the Phase 2 spec exactly (`additionalProperties` is `false`).

| Store | Schema file | Key / topic |
|---|---|---|
| Redis | [`avwap.schema.json`](avwap.schema.json) | `avwap:{symbol}:{anchor_id}` |
| Redis | [`volume_profile.schema.json`](volume_profile.schema.json) | `volume_profile:{symbol}:{session_type}` |
| Kafka + Redis | [`kill_zone_event.schema.json`](kill_zone_event.schema.json) | topic `kill_zone_events`; Redis `kill_zone:{symbol}` |

Kill-zone class-level lookup (not a Kafka payload): `kill_zone:active:{asset_class}`
holds `{kill_zone, start_time, end_time, active, asset_class}`.

Convenience pointer (same AVWAP JSON as the last write): `avwap:latest:{symbol}`.
Anchor metadata (not a wire schema): `avwap:meta:{symbol}:{anchor_id}`,
index `avwap:index:{symbol}`.

## Quant Risk Pre-Filter + setup_signals (Phase 2)

HTTP (not Kafka): [`risk_validate_request.schema.json`](risk_validate_request.schema.json)
and [`risk_validate_response.schema.json`](risk_validate_response.schema.json).
`POST /risk/validate` (default `http://localhost:8001/risk/validate`).

ML **omits `id`** on the request. Publish to `setup_signals` only when
`approved: true`, then assign `id`.

`setup_type` enum (Quant-locked + provisional slugs for Quant to add):

| Setup | `setup_type` | Performance key |
|---|---|---|
| 1 Liquidity sweep + VWAP reclaim | `sweep_reclaim` | |
| 2 FVG at VWAP / HVN | `fvg_entry` (OB overlap via `trigger_event_ids` + `order_block` factor; never `ob_fvg` on validate/publish) | |
| 3 PO3 / Judas | `po3_judas` | |
| 4 SD extension fade | `sd_extension_fade` | `4_sd_extension_fade` |
| 5 VWAP pullback continuation | `vwap_pullback_cont` | `5_vwap_pullback_cont` |
| 6 AVWAP + HTF OB confluence | `avwap_ob_confluence` | `6_avwap_ob_confluence` |

Publish-only on `setup_signals` (never on validate): `contributing_factors`
(stable factor-id enum) and `factor_breakdown` (array of
`{name, weight, score, note?}`). `sum(score)` ≈ conviction (0–100);
`confidence = conviction / 100`. Chart join is `id` + `trigger_event_ids` —
factors are labels, not substitute ids.

Validate body allow-list only: `schema_version`, `symbol`, `asset_class`,
`setup_type`, `side`, `confidence` (conviction/100), `ref_vwap`,
`ref_session`, `ts_ms`, `entry`, `stop`, `target`, `timeframe`,
`trigger_event_ids`, optional `session_type`, optional
`proposed_position_size`. Do **not** send `risk_reward`, `setup_id`,
`kill_zone*`, or a separate `conviction` field.
