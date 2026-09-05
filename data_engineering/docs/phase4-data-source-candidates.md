# Phase 4 data-source candidates (optional, no implementation)

**Status:** shopping list only. No connectors, topics, or schemas are
added in this prep. `live_trading=false`.

Existing frozen US-equities tape (do not invent aliases):

- [`schemas/options_chain.schema.json`](../../schemas/options_chain.schema.json)
  — `implied_volatility`, `open_interest`, `delta`/`gamma`/`theta`/`vega`/`rho`,
  `option_type` `call`\|`put`, `contract_symbol`, `expiry_ms`
- [`schemas/order_flow.schema.json`](../../schemas/order_flow.schema.json)
  — `aggressor` `buy`\|`sell` (same as `raw_tick`), `is_large`, `notional`

Mock only today: `MockOptionsFlow`. Live stubs raise without keys.

## Candidates

| Candidate | Why (product) | Schema / topic impact | Notes |
|---|---|---|---|
| Economic calendar / scheduled news | Setup 4 `4_sd_extension_fade` / news ≤ 15m window | **New** topic + schema, e.g. `econ_events` with `symbol?`, `ts_ms`, `event_name`, `actual`, `forecast`, `previous`, `impact`. Do **not** overload `order_flow` or `setup_signals` | Keep `ts_ms` UTC ms, uppercase symbols. Vendor TBD; no live wire |
| Headline news firehose | Same 15m news filter | Optional `news_events` `{id, ts_ms, headline, source, symbols[]}` | Dedup + delay vs calendar; not a tick |
| Deeper options Greeks vendor (OPRA / vendor greeks) | Enrich `options_chain` already on the bus | **Prefer extend optional fields** on `options_chain` (already has the five greeks + IV + OI). New vendor must map onto those names — no `iv` / `oi` / `right` | Stub: `OptionsChainConnector.parse_quote` |
| L2 / L3 order book | Liquidity / spoofing research | `raw_tick.book` already carries 5-level bids/asks. L3 (order-by-order) would need a **new** schema (`book_delta` or `book_orders`) — do not stuff into `order_flow` | High volume; partition by symbol |
| Dark-pool / off-exchange prints | Large-print confirmation | Fits **`order_flow`**: set `exchange` (e.g. venue code), `is_large=true`, `aggressor` if known. No new aliases (`side` / `taker_side` forbidden) | If aggressor unknown, do not publish until classified — do not add `aggressor=null` without a schema rev |
| Earnings / news timestamps for AVWAP | Phase 2 `earnings` / `news` anchor sources | Already: `POST /v1/anchors` + `anchor_events`. No new topic | Hooks `earnings_anchor` / `news_anchor` exist |

## Explicit non-goals (this prep)

- Do not subscribe a paid news or OPRA feed.
- Do not change `SETUP_KEYS` or Performance Snapshot ingestion.
- Do not enable live Alpaca / Binance market-data sockets.
- Do not add Kafka risk filters around any future topic.

If a candidate is approved after the paper gate, add a JSON Schema first
(field names frozen, `additionalProperties: false`) and a mock producer
before any live vendor key.
