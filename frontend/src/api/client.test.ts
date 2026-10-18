import { describe, expect, it, vi } from "vitest";
import { ApiError, request, setTestClockHeader } from "./client";
import { installFakeApi, apiError } from "../test/fakeApi";

describe("the API client", () => {
  it("sends the test clock with every request while one is set, and stops when cleared", async () => {
    const api = installFakeApi({ "GET /doctors": { body: [] } });
    setTestClockHeader("2026-11-02T08:00:00+05:30");
    await request("GET", "/doctors");
    setTestClockHeader(null);
    await request("GET", "/doctors");
    expect(api.calls[0]?.headers.get("x-test-clock")).toBe("2026-11-02T08:00:00+05:30");
    expect(api.calls[1]?.headers.has("x-test-clock")).toBe(false);
  });

  it("turns an error body into an ApiError with the code and the request id", async () => {
    installFakeApi({
      "POST /appointments": apiError(409, "SLOT_TAKEN", "Taken.", { same_patient: false }),
    });
    const failure = await request("POST", "/appointments", { body: {} }).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({
      status: 409,
      code: "SLOT_TAKEN",
      requestId: "req-test-1",
      details: { same_patient: false },
    });
  });

  it("reports an unreachable server as NETWORK_ERROR", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(request("GET", "/doctors")).rejects.toMatchObject({
      code: "NETWORK_ERROR",
      status: 0,
    });
  });

  it("copes with a reply that is not JSON, such as a proxy error page", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>Bad gateway</html>", { status: 502 })),
    );
    await expect(request("GET", "/doctors")).rejects.toMatchObject({
      code: "UNEXPECTED_RESPONSE",
      status: 502,
    });
  });

  it("returns nothing for 204 and skips empty query values", async () => {
    const api = installFakeApi({ "DELETE /doctors/1/overrides/2026-11-09": { status: 204 } });
    const result = await request("DELETE", "/doctors/1/overrides/2026-11-09", {
      query: { acknowledge_conflicts: true, empty: "", missing: undefined, nothing: null },
    });
    expect(result).toBeUndefined();
    expect(api.calls[0]?.query).toEqual({ acknowledge_conflicts: "true" });
  });

  it("sends a JSON body with the right content type", async () => {
    const api = installFakeApi({ "POST /patients": { status: 201, body: {} } });
    await request("POST", "/patients", { body: { name: "A" } });
    expect(api.calls[0]?.headers.get("content-type")).toBe("application/json");
    expect(api.calls[0]?.body).toEqual({ name: "A" });
  });
});
