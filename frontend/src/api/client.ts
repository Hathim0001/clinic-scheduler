import { getSession } from "../lib/authStore";
import type { ApiErrorBody } from "./types";

// Vite inlines this at build time (see .env.example), so changing it means rebuilding.
// The path is added when only the server address was given, so a hosting dashboard that holds
// "https://api.example.com" works as well as "https://api.example.com/api/v1".
const API_PREFIX = "/api/v1";
const configured = (
  import.meta.env.VITE_API_BASE_URL ?? `http://localhost:8000${API_PREFIX}`
).replace(/\/+$/, "");
export const API_BASE = configured.endsWith(API_PREFIX) ? configured : `${configured}${API_PREFIX}`;

// The health checks live at the server root, outside /api/v1.
export const SERVER_ROOT = API_BASE.replace(/\/api\/v1$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

// The test clock, set by ClockProvider. When present it is sent with every request.
let testClock: string | null = null;

export function setTestClockHeader(value: string | null): void {
  testClock = value;
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  body?: unknown;
  query?: Query;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

function buildUrl(path: string, query?: Query): string {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export async function request<T>(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  { body, query, signal, headers: extra }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...extra };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (testClock) headers["X-Test-Clock"] = testClock;
  const session = getSession();
  if (session) headers["Authorization"] = `Bearer ${session.token}`;

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the server.");
  }

  if (response.status === 204) return undefined as T;

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // not JSON (a proxy error page, for instance): handled below
  }

  if (!response.ok) {
    const error = (payload as ApiErrorBody | null)?.error;
    if (error && typeof error.code === "string") {
      throw new ApiError(
        response.status,
        error.code,
        error.message,
        error.details ?? {},
        error.request_id ?? response.headers.get("x-request-id"),
      );
    }
    throw new ApiError(
      response.status,
      "UNEXPECTED_RESPONSE",
      `The server answered ${response.status} in an unexpected form.`,
      {},
      response.headers.get("x-request-id"),
    );
  }
  return payload as T;
}
