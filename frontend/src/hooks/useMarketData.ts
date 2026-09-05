"use client";

import { useEffect, useRef, useState } from "react";
import { HISTORY_LIMIT } from "@/lib/constants";
import { isMockMode } from "@/lib/env";
import { fetchAvwap, fetchKillZone, fetchOhlcv, fetchSession, fetchSessions, fetchVolumeProfile, fetchVwap } from "@/lib/http";
import { avwapToVwapValues, normalizeAvwap, normalizeKillZone, normalizeVolumeProfile } from "@/lib/overlays";
import { buildMockMarketState, startMockMarket } from "@/lib/mocks/market";
import type {
  AnchorType,
  ConnectionStatus,
  KillZoneEvent,
  OHLCVBar,
  SessionLevels,
  Timeframe,
  VWAPValues,
  VolumeProfile,
} from "@/lib/types";
import { openJsonWs } from "@/lib/ws";

export interface MarketState {
  bars: OHLCVBar[];
  historyKey: string;
  lastBar: OHLCVBar | null;
  lastPrice: number | null;
  vwaps: Partial<Record<AnchorType, VWAPValues>>;
  sessions: Partial<Record<string, SessionLevels>>;
  status: ConnectionStatus;
  volumeProfile: VolumeProfile | null;
  killZone: KillZoneEvent | null;
}

const empty: MarketState = {
  bars: [],
  historyKey: "",
  lastBar: null,
  lastPrice: null,
  vwaps: {},
  sessions: {},
  status: "connecting",
  volumeProfile: null,
  killZone: null,
};

function isBar(value: unknown): value is OHLCVBar {
  if (!value || typeof value !== "object") return false;
  const v = value as OHLCVBar;
  return (
    typeof v.open_ts_ms === "number" &&
    typeof v.open === "number" &&
    typeof v.close === "number"
  );
}

function isVwap(value: unknown): value is VWAPValues {
  if (!value || typeof value !== "object") return false;
  const v = value as VWAPValues;
  return typeof v.vwap === "number" && typeof v.band_p1 === "number";
}

function mockSeed(symbol: string, timeframe: Timeframe): MarketState {
  const snap = buildMockMarketState(symbol, timeframe);
  const last = snap.last;
  return {
    bars: snap.bars,
    historyKey: `${symbol}:${timeframe}:${snap.bars[0]?.open_ts_ms ?? 0}`,
    lastBar: last,
    lastPrice: last?.close ?? null,
    vwaps: snap.vwaps,
    sessions: snap.sessions,
    status: "mock",
    volumeProfile: snap.volumeProfile,
    killZone: snap.killZone,
  };
}

function isSession(value: unknown): value is SessionLevels {
  if (!value || typeof value !== "object") return false;
  const v = value as SessionLevels;
  return typeof v.session_type === "string" && typeof v.open === "number";
}

export function useMarketData(symbol: string, timeframe: Timeframe): MarketState {
  const mocks = isMockMode();
  const streamKey = `${symbol}:${timeframe}`;
  const [state, setState] = useState<MarketState>(() =>
    mocks ? mockSeed(symbol, timeframe) : { ...empty, status: "connecting" },
  );
  const [activeKey, setActiveKey] = useState(streamKey);
  const barsRef = useRef<OHLCVBar[]>(state.bars);

  if (streamKey !== activeKey) {
    const next = mocks ? mockSeed(symbol, timeframe) : { ...empty, status: "connecting" as const };
    setActiveKey(streamKey);
    setState(next);
  }

  useEffect(() => {
    barsRef.current = [];

    if (mocks) {
      const stop = startMockMarket(symbol, timeframe, {
        onHistory: (bars) => {
          barsRef.current = bars;
          setState((prev) => ({
            ...prev,
            bars,
            historyKey: `${symbol}:${timeframe}:${bars[0]?.open_ts_ms ?? 0}`,
            lastBar: bars[bars.length - 1] ?? null,
            lastPrice: bars[bars.length - 1]?.close ?? null,
            status: "mock",
          }));
        },
        onBar: (bar) => {
          const next = barsRef.current.slice();
          const last = next[next.length - 1];
          if (last && last.open_ts_ms === bar.open_ts_ms) next[next.length - 1] = bar;
          else next.push(bar);
          if (next.length > HISTORY_LIMIT + 20) next.splice(0, next.length - HISTORY_LIMIT);
          barsRef.current = next;
          setState((prev) => ({
            ...prev,
            bars: next,
            lastBar: bar,
            lastPrice: bar.close,
          }));
        },
        onVwap: (vwap) => {
          setState((prev) => ({
            ...prev,
            vwaps: { ...prev.vwaps, [vwap.anchor_type]: vwap },
          }));
        },
        onSession: (levels) => {
          setState((prev) => ({
            ...prev,
            sessions: { ...prev.sessions, [levels.session_type]: levels },
          }));
        },
        onVolumeProfile: (volumeProfile) => {
          setState((prev) => ({ ...prev, volumeProfile }));
        },
        onKillZone: (killZone) => {
          setState((prev) => ({ ...prev, killZone }));
        },
      });
      return stop;
    }

    let alive = true;
    const stops: Array<() => void> = [];

    const applyBar = (bar: OHLCVBar) => {
      const next = barsRef.current.slice();
      const last = next[next.length - 1];
      if (last && last.open_ts_ms === bar.open_ts_ms) next[next.length - 1] = bar;
      else next.push(bar);
      barsRef.current = next;
      if (!alive) return;
      setState((prev) => ({
        ...prev,
        bars: next,
        lastBar: bar,
        lastPrice: bar.close,
      }));
    };

    (async () => {
      const [hist, vwapSnap, weeklySnap, sessionList, asiaSnap, avwapSnap, kz, vp] = await Promise.all([
        fetchOhlcv(symbol, timeframe, HISTORY_LIMIT),
        fetchVwap(symbol, "session"),
        fetchVwap(symbol, "weekly"),
        fetchSessions(symbol),
        fetchSession(symbol, "asia"),
        fetchAvwap(symbol),
        fetchKillZone(symbol),
        fetchVolumeProfile(symbol),
      ]);
      if (!alive) return;
      if (hist.length) {
        barsRef.current = hist;
        setState((prev) => ({
          ...prev,
          bars: hist,
          historyKey: `${symbol}:${timeframe}:${hist[0]?.open_ts_ms ?? 0}`,
          lastBar: hist[hist.length - 1] ?? null,
          lastPrice: hist[hist.length - 1]?.close ?? null,
        }));
      }
      if (vwapSnap) {
        setState((prev) => ({
          ...prev,
          vwaps: { ...prev.vwaps, [vwapSnap.anchor_type]: vwapSnap },
        }));
      }
      if (sessionList || asiaSnap) {
        const map: Partial<Record<string, SessionLevels>> = {};
        if (sessionList) {
          for (const row of sessionList.sessions) {
            if (row.value?.session_type) map[row.value.session_type] = row.value;
          }
        }
        if (asiaSnap?.session_type) map.asia = asiaSnap;
        setState((prev) => ({ ...prev, sessions: { ...prev.sessions, ...map } }));
      }
      const profile = normalizeVolumeProfile(vp);
      if (profile) {
        setState((prev) => ({ ...prev, volumeProfile: profile }));
      }
      const avwap = normalizeAvwap(avwapSnap);
      if (avwap) {
        setState((prev) => ({
          ...prev,
          vwaps: { ...prev.vwaps, weekly: avwapToVwapValues(avwap) },
        }));
      } else if (weeklySnap) {
        setState((prev) => ({
          ...prev,
          vwaps: { ...prev.vwaps, weekly: weeklySnap },
        }));
      }
      const zone = normalizeKillZone(kz);
      if (zone) {
        setState((prev) => ({ ...prev, killZone: zone }));
      }
    })();

    stops.push(
      openJsonWs("/v1/ws/ohlcv", { symbol, timeframe }, (data) => {
        if (isBar(data)) applyBar(data);
      }, () => undefined),
    );
    stops.push(
      openJsonWs("/v1/ws/vwap", { symbol }, (data) => {
        if (!isVwap(data)) return;
        setState((prev) => ({
          ...prev,
          vwaps: { ...prev.vwaps, [data.anchor_type]: data },
        }));
      }, (status) => {
        setState((prev) => ({ ...prev, status }));
      }),
    );
    stops.push(
      openJsonWs("/v1/ws/session", { symbol }, (data) => {
        if (!isSession(data)) return;
        setState((prev) => ({
          ...prev,
          sessions: { ...prev.sessions, [data.session_type]: data },
        }));
      }, () => undefined),
    );
    stops.push(
      openJsonWs("/v1/ws/avwap", { symbol }, (data) => {
        const avwap = normalizeAvwap(data);
        if (!avwap) return;
        setState((prev) => ({
          ...prev,
          vwaps: { ...prev.vwaps, weekly: avwapToVwapValues(avwap) },
        }));
      }, () => undefined),
    );
    stops.push(
      openJsonWs("/v1/ws/kill-zone", { symbol }, (data) => {
        const zone = normalizeKillZone(data);
        if (!zone) return;
        setState((prev) => ({ ...prev, killZone: zone }));
      }, () => undefined),
    );
    stops.push(
      openJsonWs("/v1/ws/volume-profile", { symbol }, (data) => {
        const profile = normalizeVolumeProfile(data);
        if (!profile) return;
        setState((prev) => ({ ...prev, volumeProfile: profile }));
      }, () => undefined),
    );

    return () => {
      alive = false;
      for (const stop of stops) stop();
    };
  }, [symbol, timeframe, mocks]);

  return state;
}
