const BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

async function request(path, options = {}, token = null) {
  const headers = { "Content-Type": "application/json", ...options.headers };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...options,
      headers,
    });
  } catch {
    throw new Error("Cannot reach the backend. Is it running on " + BASE + " ?");
  }
  let body = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON response */
  }
  if (!res.ok) {
    const msg = body?.error?.message || `Request failed (HTTP ${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    err.retryAfter = body?.error?.retry_after;
    throw err;
  }
  return body;
}

export const getCourses = () => request("/courses");
export const getSubjects = (course) => request(`/subjects${course ? `?course=${encodeURIComponent(course)}` : ""}`);
export const sendChat = (payload, token = null) => request("/chat", { method: "POST", body: JSON.stringify(payload) }, token);
export const deleteSession = (id, token = null) => request(`/sessions/${encodeURIComponent(id)}`, { method: "DELETE" }, token);
