import { inferAssetClass } from "../constants";
import { mockSignalFrame } from "../signals";
import type { SignalFrame } from "../types";

export function startMockSignals(
  symbol: string,
  lastPrice: () => number,
  onFrame: (frame: SignalFrame) => void,
): () => void {
  const asset = inferAssetClass(symbol);
  let seq = 0;
  const fire = () => {
    seq += 1;
    onFrame(mockSignalFrame(symbol, asset, lastPrice(), Date.now(), seq));
  };
  fire();
  const timer = setInterval(fire, 3200);
  return () => clearInterval(timer);
}
