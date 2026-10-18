import { useEffect, useRef, useSyncExternalStore } from "react";
import { useLocation } from "react-router";
import { Banner } from "./common";

const TITLES: [prefix: string, title: string][] = [
  ["/day", "Day view"],
  ["/book", "Book an appointment"],
  ["/queue", "Queue"],
  ["/patients", "Patients"],
  ["/reports", "Report"],
  ["/proof", "Prove the rules"],
  ["/staff", "Staff accounts"],
  ["/admin", "Doctors"],
];

/** The tab title for a path, so a screen-reader user and the browser history both say where they are. */
export const titleFor = (path: string): string => {
  const match = TITLES.find(([prefix]) => path === prefix || path.startsWith(`${prefix}/`));
  return match ? `${match[1]} · Clinic Scheduler` : "Clinic Scheduler";
};

/**
 * On every navigation: update the tab title and move focus to the page, because a single-page app
 * does not reload, so without this a keyboard or screen-reader user stays on the link they pressed.
 * The first render is left alone so the page does not steal focus when it opens.
 */
export function useRouteAccessibility() {
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const first = useRef(true);
  useEffect(() => {
    document.title = titleFor(pathname);
    if (first.current) {
      first.current = false;
      return;
    }
    main.current?.focus({ preventScroll: false });
  }, [pathname]);
  return main;
}

export function SkipLink() {
  return (
    <a className="skip-link" href="#main">
      Skip to the page
    </a>
  );
}

const subscribe = (notify: () => void) => {
  window.addEventListener("online", notify);
  window.addEventListener("offline", notify);
  return () => {
    window.removeEventListener("online", notify);
    window.removeEventListener("offline", notify);
  };
};

/** Says so when the browser has lost its connection, instead of leaving screens that never load. */
export function OfflineBanner() {
  const online = useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    () => true,
  );
  if (online) return null;
  return (
    <Banner kind="warn">
      You are offline. What you see may be out of date, and changes cannot be saved until the
      connection is back.
    </Banner>
  );
}
