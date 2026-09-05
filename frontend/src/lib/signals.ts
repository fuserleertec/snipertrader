import type {
  AssetClass,
  FVGZone,
  SetupSignal,
  SignalFrame,
  SignalKind,
  SignalRow,
  SweepEvent,
} from "./types";

export function isSetupSignal(frame: SignalFrame): frame is SetupSignal {
  return "setup_type" in frame && "ts_ms" in frame && "side" in frame && !("swept_level" in frame);
}

export function isFvgZone(frame: SignalFrame): frame is FVGZone {
  return "direction" in frame && "high" in frame && "low" in frame && "created_ts_ms" in frame;
}

export function isSweepEvent(frame: SignalFrame): frame is SweepEvent {
  return "swept_level" in frame;
}

export function signalKind(frame: SignalFrame): SignalKind | null {
  if (isSweepEvent(frame)) return "sweep";
  if (isFvgZone(frame)) return "fvg";
  if (isSetupSignal(frame)) return "setup";
  return null;
}

function fmtPx(n: number): string {
  return n >= 1000 ? n.toFixed(1) : n.toFixed(2);
}

export function toSignalRow(frame: SignalFrame): SignalRow | null {
  if (isSweepEvent(frame)) {
    const status =
      frame.reclaim === true ? "reclaimed" : frame.reclaim === false ? "open" : "pending";
    return {
      id: frame.id,
      ts_ms: frame.ts_ms,
      symbol: frame.symbol,
      pattern_type: "sweep",
      direction: frame.side,
      zone: `lvl ${fmtPx(frame.swept_level)}`,
      status,
      kind: "sweep",
    };
  }
  if (isFvgZone(frame)) {
    return {
      id: frame.id,
      ts_ms: frame.created_ts_ms,
      symbol: frame.symbol,
      pattern_type: "FVG",
      direction: frame.direction,
      zone: `${fmtPx(frame.low)}–${fmtPx(frame.high)}`,
      status: frame.mitigated ? "mitigated" : "open",
      kind: "fvg",
    };
  }
  if (isSetupSignal(frame)) {
    const zone =
      frame.ref_session ??
      (frame.ref_vwap != null ? `VWAP ${fmtPx(frame.ref_vwap)}` : "—");
    return {
      id: frame.id,
      ts_ms: frame.ts_ms,
      symbol: frame.symbol,
      pattern_type: frame.setup_type,
      direction: frame.side,
      zone,
      status: frame.confidence != null ? `${Math.round(frame.confidence * 100)}%` : "active",
      kind: "setup",
    };
  }
  return null;
}

export function mockSignalFrame(
  symbol: string,
  asset_class: AssetClass,
  lastClose: number,
  now_ms: number,
  seq: number,
): SignalFrame {
  const pick = seq % 3;
  const id = `${symbol}-${now_ms}-${seq}`;
  if (pick === 0) {
    const side = seq % 2 === 0 ? "long" : "short";
    const setups = ["FVG continuation", "session sweep", "VWAP reclaim", "liquidity grab"];
    const frame: SetupSignal = {
      schema_version: "1.1",
      id,
      symbol,
      asset_class,
      setup_type: setups[seq % setups.length],
      side,
      confidence: 0.55 + ((seq * 7) % 40) / 100,
      ref_vwap: lastClose,
      ref_session: asset_class === "crypto" ? "london" : "rth",
      ts_ms: now_ms,
    };
    return frame;
  }
  if (pick === 1) {
    const direction = seq % 2 === 0 ? "bullish" : "bearish";
    const width = lastClose * 0.0015;
    const frame: FVGZone = {
      schema_version: "1.1",
      id,
      symbol,
      asset_class,
      direction,
      high: lastClose + width,
      low: lastClose - width * 0.3,
      mitigated: false,
      created_ts_ms: now_ms,
      ttl_seconds: 172800,
    };
    return frame;
  }
  const frame: SweepEvent = {
    schema_version: "1.1",
    id,
    symbol,
    asset_class,
    side: seq % 2 === 0 ? "buy" : "sell",
    swept_level: lastClose * (seq % 2 === 0 ? 0.998 : 1.002),
    reclaim: seq % 5 === 0 ? true : seq % 5 === 1 ? false : null,
    ts_ms: now_ms,
  };
  return frame;
}
