import { afterEach, describe, expect, it, vi } from "vitest";
import { loadTestClock, saveTestClock } from "./clockStore";

afterEach(() => vi.restoreAllMocks());

describe("the stored test clock", () => {
  it("is kept and read back", () => {
    expect(loadTestClock()).toBeNull();
    saveTestClock("2026-11-02T08:00:00+05:30");
    expect(loadTestClock()).toBe("2026-11-02T08:00:00+05:30");
  });

  it("is forgotten when cleared", () => {
    saveTestClock("2026-11-02T08:00:00+05:30");
    saveTestClock(null);
    expect(loadTestClock()).toBeNull();
  });

  it("does not break the page when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(loadTestClock()).toBeNull();
    expect(() => saveTestClock("2026-11-02T08:00:00+05:30")).not.toThrow();
  });
});
