import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { setTestClockHeader } from "../api/client";

// Pages load several queries; on a busy machine (or CI) the default one second is sometimes too short.
configure({ asyncUtilTimeout: 4000 });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.localStorage.clear();
  window.sessionStorage.clear();
  setTestClockHeader(null);
});
