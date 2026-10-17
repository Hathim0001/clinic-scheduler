import { vi } from "vitest";

export interface Call {
  method: string;
  path: string; // without the /api/v1 prefix
  query: Record<string, string>;
  body: unknown;
  headers: Headers;
}

export interface Reply {
  status?: number;
  body?: unknown;
}

type Route = Reply | ((call: Call) => Reply);

/** A standard API error body, as the server sends it. */
export function apiError(
  status: number,
  code: string,
  message: string,
  details: Record<string, unknown> = {},
): Reply {
  return { status, body: { error: { code, message, details, request_id: "req-test-1" } } };
}

/**
 * Replaces fetch with a router for the API. Routes are keyed "METHOD /path" (the path without the
 * /api/v1 prefix; health checks use their root path). A request nobody expected is a 404, so a test
 * fails loudly when the page calls something it should not.
 */
export function installFakeApi(routes: Record<string, Route>) {
  const calls: Call[] = [];
  const all: Record<string, Route> = { "GET /readyz": { body: { status: "ready" } }, ...routes };

  const fake = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const call: Call = {
      method,
      path,
      query: Object.fromEntries(url.searchParams),
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
      headers: new Headers(init?.headers),
    };
    calls.push(call);
    const route = all[`${method} ${path}`];
    const reply: Reply =
      route === undefined
        ? apiError(404, "NOT_FOUND", `No fake route for ${method} ${path}`)
        : typeof route === "function"
          ? route(call)
          : route;
    const status = reply.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(reply.body ?? {}), {
      status,
      headers: { "content-type": "application/json", "x-request-id": "req-test-1" },
    });
  });
  vi.stubGlobal("fetch", fake);

  return {
    calls,
    count: (method: string, path: string) =>
      calls.filter((call) => call.method === method && call.path === path).length,
    last: (method: string, path: string) =>
      [...calls].reverse().find((call) => call.method === method && call.path === path),
  };
}
