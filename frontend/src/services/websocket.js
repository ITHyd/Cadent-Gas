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

export const connectWebSocket = (sessionId) => {
  const token = localStorage.getItem('access_token');
  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
  const url = `${getWsBaseUrl()}/api/v1/agents/ws/${sessionId}${tokenParam}`;

  const ws = new WebSocket(url);

  ws.onerror = (event) => {
    console.error('[WebSocket] Connection error:', event);
  };

  return ws;
};
