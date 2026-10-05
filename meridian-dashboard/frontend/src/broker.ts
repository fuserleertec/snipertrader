/**
 * Alpaca stock broker (UI side). Talks to the existing FastAPI routes.
 * This client never sends secrets. Connect is deploy/disconnect.
 * Start Trading is a local arm flag — this module does not place orders.
 */
import { BASE } from './api';

export interface BrokerStatus {
  connected: boolean;
  mode: string;
  deployed?: boolean;
  badge?: string;
  reason?: string;
  account_id?: string;
  equity?: number;
  buying_power?: number;
  account_status?: string;
}

async function call(path: string, method: 'GET' | 'POST'): Promise<BrokerStatus> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), 10000);
  try {
    const r = await fetch(`${BASE}${path}`, { method, signal: ctrl.signal });
    if (!r.ok) {
      let detail = '';
      try {
        const j = await r.json();
        detail = j.detail || j.reason || '';
      } catch {
        /* non-JSON */
      }
      throw new Error(detail || `${path} -> ${r.status}`);
    }
    const body = await r.json() as { broker?: BrokerStatus };
    if (!body.broker) throw new Error(`${path} returned no broker`);
    return body.broker;
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw new Error(`${path} timed out`);
    throw e;
  } finally {
    window.clearTimeout(timer);
  }
}

export function uiStateLabel(st: BrokerStatus | null): string {
  if (!st) return 'UNKNOWN';
  if (st.badge) return st.badge.toUpperCase();
  if (st.connected) return `${(st.mode || 'PAPER').toUpperCase()} · CONNECTED`;
  return 'DISCONNECTED';
}

export const equityBroker = {
  status: () => call('/api/broker', 'GET'),
  connect: () => call('/api/broker/deploy', 'POST'),
  disconnect: () => call('/api/broker/disconnect', 'POST'),
};
