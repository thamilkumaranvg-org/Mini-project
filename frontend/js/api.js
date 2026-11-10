/**
 * Unified API Client for Farmer Slot Booking System
 * Handles credentials, X-Requested-With header, JSON serialization, and 401 handling.
 */
import { showToast } from "./ui.js";

export class ApiError extends Error {
  constructor(status, code, message, details = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export async function apiRequest(endpoint, options = {}) {
  const url = endpoint.startsWith("http") ? endpoint : endpoint;
  const method = (options.method || "GET").toUpperCase();

  const headers = {
    "X-Requested-With": "fetch",
    ...(options.headers || {})
  };

  if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }

  const fetchOptions = {
    method,
    headers,
    credentials: "include", // send httpOnly cookies automatically
    ...options
  };

  try {
    const res = await fetch(url, fetchOptions);

    // Check if CSV or blob response
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("text/csv") || contentType.includes("application/octet-stream")) {
      if (!res.ok) throw new ApiError(res.status, "EXPORT_FAILED", "File download failed");
      return await res.blob();
    }

    let data;
    try {
      data = await res.json();
    } catch {
      data = null;
    }

    if (res.status === 401) {
      if (!url.includes("/login")) {
        handleUnauthorizedRedirect();
      }
      const errMsg = data?.error?.message || "Invalid email or password.";
      const errCode = data?.error?.code || "UNAUTHORIZED";
      throw new ApiError(401, errCode, errMsg, data?.error?.details || {});
    }

    if (!res.ok) {
      const errCode = data?.error?.code || `HTTP_${res.status}`;
      const errMsg = data?.error?.message || "An unexpected error occurred.";
      const errDetails = data?.error?.details || {};
      throw new ApiError(res.status, errCode, errMsg, errDetails);
    }

    return data;
  } catch (err) {
    if (err instanceof ApiError) {
      throw err;
    }
    throw new ApiError(0, "NETWORK_ERROR", "Network connection failed. Please check your internet connection.");
  }
}

function handleUnauthorizedRedirect() {
  const path = window.location.pathname;
  // Prevent infinite loops if already on a login page
  if (path.endsWith("login.html") || path.endsWith("register.html") || path === "/" || path.endsWith("index.html")) {
    return;
  }

  if (path.includes("/admin/")) {
    window.location.href = "/admin/login.html";
  } else if (path.includes("/officer/")) {
    window.location.href = "/officer/login.html";
  } else if (path.includes("/scanner/")) {
    window.location.href = "/scanner/login.html";
  } else {
    window.location.href = "/login.html";
  }
}

