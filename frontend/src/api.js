
const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export async function apiRequest(path, options = {}) {
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...(options.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...options.headers,
      },
    });
  } catch {
    throw new Error(
      `Cannot connect to backend at ${API_BASE_URL}. Check that the backend is running.`
    );
  }

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail =
      typeof data === "object" && data !== null
        ? data.detail || data.message
        : data;

    const message = Array.isArray(detail)
      ? detail
          .map((item) => {
            const field = item.loc?.slice(1).join(".");
            return `${field ? `${field}: ` : ""}${item.msg || JSON.stringify(item)}`;
          })
          .join("; ")
      : typeof detail === "string"
        ? detail
        : JSON.stringify(detail || `HTTP ${response.status}`);

    throw new Error(`Request failed (${response.status}): ${message}`);
  }

  return data;
}
