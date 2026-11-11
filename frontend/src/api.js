const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

function errorMessage(detail) {
  if (Array.isArray(detail)) return detail.map(errorMessage).join(" ");
  if (detail && typeof detail === "object") {
    const field = (detail.loc || []).filter((part) => part !== "body").join(".");
    return `${field ? `${field}: ` : ""}${detail.msg || "Invalid input."}`;
  }
  return String(detail || "Request failed.");
}

async function request(path, options = {}) {
  const { token, signal, ...fetchOptions } = options;
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener("abort", abort, { once: true });
  const timeout = setTimeout(abort, 20000);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...fetchOptions, signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...fetchOptions.headers }
    });
    const body = response.headers.get("content-type")?.includes("application/json") ? await response.json() : null;
    if (!response.ok) throw new ApiError(errorMessage(body?.detail || body?.message), response.status);
    return body;
  } catch (error) {
    if (controller.signal.aborted && !signal?.aborted) throw new ApiError("Request timed out. Please retry.", 408);
    throw error;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}

export function login(email, password, options = {}) {
  return request("/api/auth/login", { ...options, method: "POST", body: JSON.stringify({ email, password }) });
}
export function logout(token) { return request("/api/auth/logout", { token, method: "POST" }); }
export function getMe(token, options = {}) { return request("/api/auth/me", { ...options, token }); }
export function listSuppliers(token, options = {}) { return request("/api/auth/suppliers", { ...options, token }); }
export function listAuctions(token, params = {}, options = {}) {
  const query = new URLSearchParams({ limit: String(params.limit || 25), offset: String(params.offset || 0) });
  return request(`/api/rfqs?${query}`, { ...options, token });
}
export function getAuction(id, token, params = {}, options = {}) {
  const query = new URLSearchParams(params);
  return request(`/api/rfqs/${id}${query.size ? `?${query}` : ""}`, { ...options, token });
}
export function createAuction(payload, token, options = {}) {
  return request("/api/rfqs", { ...options, token, method: "POST", body: JSON.stringify(payload) });
}
export function submitBid(id, payload, token, options = {}) {
  return request(`/api/rfqs/${id}/bids`, { ...options, token, method: "POST", body: JSON.stringify(payload) });
}
