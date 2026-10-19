import { useEffect } from "react";

const TARGETS = ".card, .glance-item, .hero, .stat-card, .tickets tbody tr";

/**
 * A soft light that follows the pointer across a card: the position is handed to the stylesheet as
 * two custom properties and the stylesheet decides what to draw. Touch screens and a reduced-motion
 * setting get nothing, and nothing here changes what a card says or does.
 */
export function useSpotlight() {
  useEffect(() => {
    if (
      typeof window.matchMedia !== "function" ||
      window.matchMedia("(prefers-reduced-motion: reduce), (hover: none)").matches
    ) {
      return;
    }
    let frame = 0;
    const onMove = (event: PointerEvent) => {
      const card = (event.target as Element | null)?.closest<HTMLElement>(TARGETS);
      if (!card) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const box = card.getBoundingClientRect();
        card.style.setProperty("--mx", `${event.clientX - box.left}px`);
        card.style.setProperty("--my", `${event.clientY - box.top}px`);
      });
    };
    document.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      document.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(frame);
    };
  }, []);
}
