import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { SERVER_ROOT } from "../api/client";
import { Banner } from "./common";

async function checkReady(): Promise<true> {
  const response = await fetch(`${SERVER_ROOT}/readyz`);
  if (!response.ok) throw new Error("not ready");
  return true;
}

/**
 * The free hosting plan puts the server to sleep when idle, so the first call can take about a
 * minute. If the server has not answered after 3 seconds, say so instead of showing a blank page.
 */
export function WakeBanner() {
  const ready = useQuery({
    queryKey: ["ready"],
    queryFn: checkReady,
    retry: true,
    retryDelay: 2000,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  const [waited, setWaited] = useState(false);
  const isReady = ready.isSuccess;

  useEffect(() => {
    if (isReady) return;
    const timer = setTimeout(() => setWaited(true), 3000);
    return () => clearTimeout(timer);
  }, [isReady]);

  if (isReady || !waited) return null;
  return <Banner kind="warn">Waking the server, this can take up to a minute…</Banner>;
}
