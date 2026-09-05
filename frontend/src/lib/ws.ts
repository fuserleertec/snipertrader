import { wsUrl } from "./env";
import type { ConnectionStatus } from "./types";

export type JsonHandler = (data: unknown) => void;

/**
 * One socket per URL (query-param subscribe only — no multiplex JSON).
 * Reconnect with a new URL to change symbol.
 */
export function openJsonWsAt(
  url: string,
  onMessage: JsonHandler,
  onStatus: (status: ConnectionStatus) => void,
): () => void {
  let socket: WebSocket | null = null;
  let closed = false;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const connect = () => {
    if (closed) return;
    onStatus("connecting");
    try {
      socket = new WebSocket(url);
    } catch {
      onStatus("disconnected");
      schedule();
      return;
    }
    socket.onopen = () => {
      attempt = 0;
      onStatus("live");
    };
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(String(event.data)) as unknown;
        onMessage(data);
      } catch {
        /* ignore malformed frames */
      }
    };
    socket.onerror = () => {
      /* onclose handles retry */
    };
    socket.onclose = () => {
      if (closed) return;
      onStatus("disconnected");
      schedule();
    };
  };

  const schedule = () => {
    if (closed) return;
    const delay = Math.min(8000, 400 * 2 ** attempt);
    attempt += 1;
    timer = setTimeout(connect, delay);
  };

  connect();

  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    socket?.close();
  };
}

export function openJsonWs(
  path: string,
  params: Record<string, string>,
  onMessage: JsonHandler,
  onStatus: (status: ConnectionStatus) => void,
): () => void {
  return openJsonWsAt(wsUrl(path, params), onMessage, onStatus);
}
