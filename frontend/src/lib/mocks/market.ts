import {
  HISTORY_LIMIT,
  inferAssetClass,
  seedPrice,
  sessionsForAsset,
  TF_MS,
} from "../constants";
import { sessionWindows } from "../sessions";
import type {
  AnchorType,
  OHLCVBar,
  SessionLevels,
  Timeframe,
  VWAPValues,
} from "../types";
import { computeSessionLevels, computeVwap } from "../vwap";

export interface MockMarketHandlers {
  onHistory: (bars: OHLCVBar[]) => void;
  onBar: (bar: OHLCVBar) => void;
  onVwap: (vwap: VWAPValues) => void;
  onSession: (levels: SessionLevels) => void;
}

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function align(ms: number, tf: Timeframe): number {
  const step = TF_MS[tf];
  return Math.floor(ms / step) * step;
}

function pushBar(bars: OHLCVBar[], bar: OHLCVBar): void {
  const last = bars[bars.length - 1];
  if (last && last.open_ts_ms === bar.open_ts_ms) {
    bars[bars.length - 1] = bar;
  } else {
    bars.push(bar);
    if (bars.length > HISTORY_LIMIT + 20) {
      bars.splice(0, bars.length - HISTORY_LIMIT);
    }
  }
}

function emitState(
  bars: OHLCVBar[],
  symbol: string,
  handlers: MockMarketHandlers,
  now: number,
): void {
  const asset = inferAssetClass(symbol);
  const sessionType = sessionsForAsset(asset)[0] ?? "london";
  const anchors: AnchorType[] = ["session", "weekly", "rolling"];
  for (const anchor of anchors) {
    const snap = computeVwap(bars, {
      symbol,
      asset_class: asset,
      anchor_type: anchor,
      session_type: anchor === "session" ? sessionType : null,
      now_ms: now,
    });
    if (snap) handlers.onVwap(snap);
  }
  // Prefer the currently active session type for session-anchored VWAP.
  const activeWin = sessionWindows(asset, now).find(
    (w) => now >= w.start_ms && now < w.end_ms && sessionsForAsset(asset).includes(w.session_type),
  );
  if (activeWin) {
    const snap = computeVwap(bars, {
      symbol,
      asset_class: asset,
      anchor_type: "session",
      session_type: activeWin.session_type,
      now_ms: now,
    });
    if (snap) handlers.onVwap(snap);
  }
  const seen = new Set<string>();
  for (const win of sessionWindows(asset, now)) {
    if (!sessionsForAsset(asset).includes(win.session_type)) continue;
    if (win.end_ms < now - 86_400_000 || win.start_ms > now + 3_600_000) continue;
    const key = `${win.session_type}:${win.start_ms}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const levels = computeSessionLevels(bars, win, symbol, asset, now);
    if (levels) handlers.onSession(levels);
  }
}

export function buildMockHistory(symbol: string, timeframe: Timeframe, now = Date.now()): OHLCVBar[] {
  const asset = inferAssetClass(symbol);
  const step = TF_MS[timeframe];
  const rand = mulberry32(hash(`${symbol}:${timeframe}`));
  const lastOpen = align(now, timeframe);
  let price = seedPrice(symbol);
  const vol = price * 0.0012;
  const bars: OHLCVBar[] = [];

  for (let i = HISTORY_LIMIT; i >= 1; i--) {
    const openTs = lastOpen - i * step;
    const drift = (rand() - 0.48) * vol;
    const open = price;
    const close = Math.max(0.01, open + drift);
    const high = Math.max(open, close) + rand() * vol * 0.6;
    const low = Math.min(open, close) - rand() * vol * 0.6;
    const volume = 8 + rand() * 40;
    bars.push({
      schema_version: "1.1",
      symbol,
      asset_class: asset,
      timeframe,
      open_ts_ms: openTs,
      close_ts_ms: openTs + step,
      open,
      high,
      low,
      close,
      volume,
      n_ticks: 20 + Math.floor(rand() * 80),
      buy_volume: volume * (0.45 + rand() * 0.2),
      sell_volume: volume * (0.35 + rand() * 0.2),
      closed: true,
    });
    price = close;
  }
  return bars;
}

export function startMockMarket(
  symbol: string,
  timeframe: Timeframe,
  handlers: MockMarketHandlers,
): () => void {
  const now = Date.now();
  const bars = buildMockHistory(symbol, timeframe, now);
  const last = bars[bars.length - 1];
  let price = last?.close ?? seedPrice(symbol);
  const step = TF_MS[timeframe];
  const lastOpen = align(now, timeframe);
  const rand = mulberry32(hash(`${symbol}:${timeframe}:live`));
  const vol = price * 0.0012;
  const asset = inferAssetClass(symbol);

  handlers.onHistory(bars.slice());
  emitState(bars, symbol, handlers, now);

  let forming: OHLCVBar = {
    schema_version: "1.1",
    symbol,
    asset_class: asset,
    timeframe,
    open_ts_ms: lastOpen,
    close_ts_ms: lastOpen + step,
    open: price,
    high: price,
    low: price,
    close: price,
    volume: 1,
    n_ticks: 1,
    closed: false,
  };
  pushBar(bars, forming);
  handlers.onBar(forming);

  const tickMs = timeframe === "1m" || timeframe === "5m" ? 280 : 450;
  const timer = setInterval(() => {
    const t = Date.now();
    const openTs = align(t, timeframe);
    const tick = (rand() - 0.49) * vol * 0.35;
    if (openTs !== forming.open_ts_ms) {
      forming = { ...forming, closed: true, close_ts_ms: forming.open_ts_ms + step };
      pushBar(bars, forming);
      handlers.onBar(forming);
      const open = forming.close;
      forming = {
        schema_version: "1.1",
        symbol,
        asset_class: asset,
        timeframe,
        open_ts_ms: openTs,
        close_ts_ms: openTs + step,
        open,
        high: open,
        low: open,
        close: open,
        volume: 1 + rand() * 2,
        n_ticks: 1,
        closed: false,
      };
    } else {
      const close = Math.max(0.01, forming.close + tick);
      forming = {
        ...forming,
        close,
        high: Math.max(forming.high, close),
        low: Math.min(forming.low, close),
        volume: forming.volume + 0.4 + rand() * 1.8,
        n_ticks: forming.n_ticks + 1,
        closed: false,
      };
    }
    pushBar(bars, forming);
    handlers.onBar(forming);
    emitState(bars, symbol, handlers, t);
  }, tickMs);

  return () => clearInterval(timer);
}
