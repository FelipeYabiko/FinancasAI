// Thin fetch wrapper: JSON in/out, CSRF header on writes, 401 -> login screen.

function csrfToken() {
  const m = document.cookie.match(/(?:^|;\s*)fia_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : "Erro na requisição");
    this.status = status;
    this.detail = detail;
  }
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

function errorMessage(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ");
  }
  return "Erro na requisição";
}

export async function api(path, { method = "GET", body, params, raw = false } = {}) {
  let url = path;
  if (params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, v);
    }
    const s = qs.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }
  const headers = {};
  const opts = { method, headers, credentials: "same-origin" };
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    onUnauthorized();
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch (_) {
      /* not JSON */
    }
    throw new ApiError(res.status, errorMessage(detail));
  }
  if (raw) return res;
  if (res.status === 204) return null;
  return res.json();
}

export const get = (p, params) => api(p, { params });
export const post = (p, body, params) => api(p, { method: "POST", body, params });
export const put = (p, body) => api(p, { method: "PUT", body });
export const patch = (p, body) => api(p, { method: "PATCH", body });
export const del = (p, params) => api(p, { method: "DELETE", params });
