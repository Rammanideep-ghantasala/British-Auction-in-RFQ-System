const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const { token, ...fetchOptions } = options;
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(fetchOptions.headers || {})
  };

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...fetchOptions,
    headers
  });

  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    const detail = body?.detail || body?.message || "Request failed.";
    throw new Error(Array.isArray(detail) ? detail.join(" ") : detail);
  }

  return body;
}

export function login(email, password) {
  return request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
}

export function getMe(token) {
  return request("/api/auth/me", { token });
}

export function listSuppliers(token) {
  return request("/api/auth/suppliers", { token });
}

export function listAuctions(token, params = {}) {
  const query = new URLSearchParams({
    limit: String(params.limit || 25),
    offset: String(params.offset || 0)
  });
  return request(`/api/rfqs?${query.toString()}`, { token });
}

export function getAuction(id, token) {
  return request(`/api/rfqs/${id}`, { token });
}

export function createAuction(payload, token) {
  return request("/api/rfqs", {
    token,
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function submitBid(id, payload, token) {
  return request(`/api/rfqs/${id}/bids`, {
    token,
    method: "POST",
    body: JSON.stringify(payload)
  });
}
