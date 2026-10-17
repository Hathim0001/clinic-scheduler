import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { setTestClockHeader } from "../api/client";
import { loadTestClock, saveTestClock } from "./clockStore";

interface ClockContextValue {
  /** The test clock as sent to the API (an ISO time with +05:30), or null for the real clock. */
  testClock: string | null;
  setTestClock: (isoWithOffset: string) => void;
  clearTestClock: () => void;
}

const ClockContext = createContext<ClockContextValue | null>(null);

export function ClockProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [testClock, setState] = useState<string | null>(() => {
    const stored = loadTestClock();
    setTestClockHeader(stored); // before the first request goes out
    return stored;
  });

  const apply = useCallback(
    (value: string | null) => {
      setTestClockHeader(value);
      saveTestClock(value);
      setState(value);
      void queryClient.invalidateQueries(); // everything on screen depends on "now"
    },
    [queryClient],
  );

  const value = useMemo<ClockContextValue>(
    () => ({
      testClock,
      setTestClock: (iso) => apply(iso),
      clearTestClock: () => apply(null),
    }),
    [testClock, apply],
  );
  return <ClockContext.Provider value={value}>{children}</ClockContext.Provider>;
}

export function useTestClock(): ClockContextValue {
  const value = useContext(ClockContext);
  if (!value) throw new Error("useTestClock must be used inside ClockProvider");
  return value;
}
