"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LIST_REFRESH_MS, LIST_REFRESH_SEC } from "@/lib/constants";
import { clampRefreshSec } from "@/lib/desk";

/**
 * SWR-style list cadence. Automatic poll is never faster than 15 minutes
 * (`refresh_sec` from Quant, default 900). Manual REFRESH still bumps immediately.
 */
export function useListRefresh(refreshSec = LIST_REFRESH_SEC) {
  const intervalMs = clampRefreshSec(refreshSec) * 1000;
  const [tick, setTick] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const nextAt = useRef(Date.now() + intervalMs);

  const bump = useCallback(() => {
    nextAt.current = Date.now() + intervalMs;
    setTick((n) => n + 1);
    setNow(Date.now());
  }, [intervalMs]);

  useEffect(() => {
    nextAt.current = Date.now() + intervalMs;
    const poll = window.setInterval(bump, intervalMs);
    const clock = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => {
      window.clearInterval(poll);
      window.clearInterval(clock);
    };
  }, [bump, intervalMs]);

  const remainMs = Math.max(0, nextAt.current - now);
  return {
    tick,
    refreshNow: bump,
    nextAtMs: nextAt.current,
    remainMs,
    refreshSec: intervalMs / 1000,
    intervalMs: intervalMs || LIST_REFRESH_MS,
  };
}

export function formatRemain(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m >= 1) return `${m}m ${String(s).padStart(2, "0")}s`;
  return `${s}s`;
}

export function formatEt(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    minute: "2-digit",
  });
}
