const API_BASE = window.location.origin.startsWith("file") ? "http://127.0.0.1:8000" : "";

export async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

export function alertSocket() {
  const base = API_BASE || window.location.origin;
  return new WebSocket(`${base.replace(/^http/, "ws")}/ws/alerts`);
}

export function formatTime(value, includeDate = false) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    ...(includeDate ? { day: "2-digit", month: "short" } : {}),
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value * 1000));
}

export function relativeTime(value) {
  if (!value) return "unknown";
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - value));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
