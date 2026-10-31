// REST client. Access token lives only in memory (not localStorage → not
// exfiltratable by XSS persistence); the refresh token is an httpOnly cookie.
let accessToken = null;
let refreshing = null;

export class ApiError extends Error {
  constructor(status, detail) { super(detail || `HTTP ${status}`); this.status = status; }
}

async function parse(r) {
  if (r.status === 204) return null;
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    let d = body && body.detail;
    if (Array.isArray(d)) d = d.map((e) => e.msg).join("; ");
    throw new ApiError(r.status, d);
  }
  return body;
}

export async function refresh() {
  if (!refreshing) {
    refreshing = fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" })
      .then(parse)
      .then((t) => { accessToken = t.access_token; return true; })
      .catch(() => { accessToken = null; return false; })
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}

export async function api(path, { method = "GET", body, retry = true } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const r = await fetch(path, {
    method, headers, credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401 && retry && !path.startsWith("/api/auth/")) {
    if (await refresh()) return api(path, { method, body, retry: false });
    window.dispatchEvent(new Event("auth:expired"));
  }
  return parse(r);
}

export async function login(email, password) {
  const t = await api("/api/auth/login", { method: "POST", body: { email, password } });
  accessToken = t.access_token;
}

export async function register(email, password, full_name) {
  const t = await api("/api/auth/register", { method: "POST", body: { email, password, full_name } });
  accessToken = t.access_token;
}

export async function logout() {
  try { await api("/api/auth/logout", { method: "POST" }); } finally { accessToken = null; }
}

export function wsUrl(path, ticket) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}${path}?ticket=${encodeURIComponent(ticket)}`;
}
