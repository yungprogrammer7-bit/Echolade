// Thin fetch wrapper. Adds the per-launch session token to every state-changing request.
const token = document.querySelector('meta[name="echolade-token"]')?.content || "";

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = {};
  if (method !== "GET") headers["X-Echolade-Token"] = token;
  const opts = { method, headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new ApiError("Can’t reach Echolade. Make sure its window is still open.", 0);
  }
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail; } catch { /* not JSON */ }
    throw new ApiError(typeof detail === "string" && detail ? detail : `Request failed (${res.status}).`, res.status);
  }
  return res.status === 204 ? null : res.json();
}
