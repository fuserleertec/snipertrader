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
  KillZoneEvent,
  OHLCVBar,
  SessionLevels,
  SessionType,
  Timeframe,
  VWAPValues,
  VolumeProfile,
} from "../types";
import { computeSessionLevels, computeVwap } from "../vwap";
import { MOCK_NOW } from "./universe";

export interface MockMarketHandlers {
  onHistory: (bars: OHLCVBar[]) => void;
  onBar: (bar: OHLCVBar) => void;
  onVwap: (vwap: VWAPValues) => void;
  onSession: (levels: SessionLevels) => void;
  onVolumeProfile?: (profile: VolumeProfile) => void;
  onKillZone?: (zone: KillZoneEvent) => void;
}

export function mockVolumeProfile(
  symbol: string,
  price: number,
  session_type: SessionLevels["session_type"],
): VolumeProfile {
  return {
    symbol,
    session_type,
    high_volume_nodes: [
      { price: price * 0.9988, volume: 1200 },
      { price: price * 1.0012, volume: 900 },
    ],
    low_volume_nodes: [{ price: price * 1.004, volume: 80 }],
    poc: price,
    timestamp: MOCK_NOW,
  };
}

export function mockKillZone(
  symbol: string,
  sessions: Partial<Record<string, SessionLevels>>,
  now: number,
): KillZoneEvent | null {
  const order: SessionType[] = ["asia", "london", "ny_am", "ny_pm", "rth", "eth", "globex"];
  let active: SessionLevels | null = null;
  let fallback: SessionLevels | null = sessions.asia ?? null;
  for (const type of order) {
    const row = sessions[type];
    if (!row) continue;
    if (!fallback) fallback = row;
    if (now >= row.session_start_ms && now < row.session_end_ms) {
      active = row;
      break;
    }
  }
  const src = active ?? fallback;
  if (!src) return null;
  return {
    symbol,
    kill_zone: src.session_type,
    start_time: src.session_start_ms,
    end_time: src.session_end_ms,
    active: now >= src.session_start_ms && now < src.session_end_ms,
    asset_class: src.asset_class,
  };
}

export function collectMockOverlays(
  bars: OHLCVBar[],
  symbol: string,
  now: number,
): {
  vwaps: Partial<Record<AnchorType, VWAPValues>>;
  sessions: Partial<Record<string, SessionLevels>>;
} {
  const asset = inferAssetClass(symbol);
  const vwaps: Partial<Record<AnchorType, VWAPValues>> = {};
  const sessions: Partial<Record<string, SessionLevels>> = {};
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
    if (snap) vwaps[anchor] = snap;
  }
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
    if (snap) vwaps.session = snap;
  }
  const seen = new Set<string>();
  for (const win of sessionWindows(asset, now)) {
    if (!sessionsForAsset(asset).includes(win.session_type)) continue;
    if (win.end_ms < now - 86_400_000 || win.start_ms > now + 3_600_000) continue;
    const key = `${win.session_type}:${win.start_ms}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const levels = computeSessionLevels(bars, win, symbol, asset, now);
    if (levels) sessions[levels.session_type] = levels;
  }
  return { vwaps, sessions };
}

export function buildMockMarketState(symbol: string, timeframe: Timeframe) {
  const now = MOCK_NOW;
  const bars = buildMockHistory(symbol, timeframe, now);
  const { vwaps, sessions } = collectMockOverlays(bars, symbol, now);
  const last = bars[bars.length - 1] ?? null;
  const price = last?.close ?? seedPrice(symbol);
  const sessionType =
    sessions.asia?.session_type ??
    (Object.values(sessions)[0]?.session_type as SessionType | undefined) ??
    "london";
  return {
    bars,
    vwaps,
    sessions,
    volumeProfile: mockVolumeProfile(symbol, price, sessionType),
    killZone: mockKillZone(symbol, sessions, now),
    last,
    now,
  };
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
  const { vwaps, sessions } = collectMockOverlays(bars, symbol, now);
  for (const snap of Object.values(vwaps)) {
    if (snap) handlers.onVwap(snap);
  }
  for (const levels of Object.values(sessions)) {
    if (levels) handlers.onSession(levels);
  }
  const last = bars[bars.length - 1];
  const price = last?.close ?? seedPrice(symbol);
  const sessionType =
    sessions.asia?.session_type ??
    (Object.values(sessions)[0]?.session_type as SessionType | undefined) ??
    "london";
  handlers.onVolumeProfile?.(mockVolumeProfile(symbol, price, sessionType));
  const kz = mockKillZone(symbol, sessions, now);
  if (kz) handlers.onKillZone?.(kz);
}

export function buildMockHistory(symbol: string, timeframe: Timeframe, now = MOCK_NOW): OHLCVBar[] {
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
  const now = MOCK_NOW;
  const bars = buildMockHistory(symbol, timeframe, now);
  const last = bars[bars.length - 1];
  const price = last?.close ?? seedPrice(symbol);
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
    const tick = (rand() - 0.49) * vol * 0.35;
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
    pushBar(bars, forming);
    handlers.onBar(forming);
    emitState(bars, symbol, handlers, now);
  }, tickMs);

  return () => clearInterval(timer);
}
