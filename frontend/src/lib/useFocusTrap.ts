import { useEffect, type RefObject } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Keeps keyboard focus inside a menu or dialog while it is open: focus moves in when it opens, Tab
 * and Shift+Tab wrap around instead of leaving for the page behind, Escape closes it, the page
 * behind does not scroll, and focus goes back to what had it before when it closes.
 */
export function useFocusTrap(
  container: RefObject<HTMLElement | null>,
  active: boolean,
  onEscape?: () => void,
) {
  useEffect(() => {
    const root = container.current;
    if (!active || !root) return;
    const before = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const items = () => Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));
    (items()[0] ?? root).focus();
    document.body.classList.add("no-scroll");

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onEscape?.();
        return;
      }
      if (event.key !== "Tab") return;
      const list = items();
      if (list.length === 0) {
        event.preventDefault();
        return;
      }
      const first = list[0]!;
      const last = list[list.length - 1]!;
      const at = document.activeElement;
      if (event.shiftKey && (at === first || !root.contains(at))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (at === last || !root.contains(at))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("no-scroll");
      before?.focus();
    };
    // the trap is set up when it opens and torn down when it closes; the callback may change freely
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);
}
