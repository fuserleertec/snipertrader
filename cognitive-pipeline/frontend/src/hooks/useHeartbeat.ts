import { useEffect } from 'react';
import { useAppStore } from '../stores/appStore';
import type { HeartbeatPayload } from '../types';

/**
 * Connects to the heartbeat WebSocket and dispatches each full-state frame
 * into the Zustand store. Reconnects with a 2s backoff on drop.
 */
export function useHeartbeat() {
  const setHeartbeat = useAppStore((s) => s.setHeartbeat);
  const setConnected = useAppStore((s) => s.setConnected);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const url =
        (import.meta.env.VITE_WS_URL as string | undefined) ||
        `ws://${window.location.hostname}:8787`;
      ws = new WebSocket(url);

      ws.onopen = () => setConnected(true);
      ws.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data) as HeartbeatPayload;
          setHeartbeat(payload);
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retryTimer = setTimeout(connect, 2000);
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      ws?.close();
    };
  }, [setHeartbeat, setConnected]);
}
