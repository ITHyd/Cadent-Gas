import { ensureFreshAccessToken } from "./api";

/**
 * Build a WebSocket URL dynamically from the current browser location.
 * In development, Vite's proxy (ws: true) forwards /api/* WS connections
 * to the backend. In production, the same origin serves everything.
 * No .env variables needed — works on any laptop after clone.
 */
const getWsBaseUrl = () => {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}`;
};

export const connectWebSocket = async (sessionId) => {
  const token = await ensureFreshAccessToken({ minValiditySeconds: 60 });
  if (!token) {
    throw new Error("Your session expired. Please sign in again.");
  }

  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
  const url = `${getWsBaseUrl()}/api/v1/agents/ws/${sessionId}${tokenParam}`;

  const ws = new WebSocket(url);

  ws.onerror = (event) => {
    console.error('[WebSocket] Connection error:', event);
  };

  return ws;
};
