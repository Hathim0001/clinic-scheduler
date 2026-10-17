import { useClockInfo } from "../api/hooks";

/** Today's India date (YYYY-MM-DD) by the clock the server is using, or "" until it has answered. */
export function useToday(): string {
  const info = useClockInfo();
  return info.data ? info.data.now_ist.slice(0, 10) : "";
}
