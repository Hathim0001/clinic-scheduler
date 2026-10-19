import { useEffect, useRef, useState } from "react";

/** Motion is decoration: a person who asked their system for less of it gets the final picture. */
function prefersStill(): boolean {
  return (
    typeof window === "undefined" ||
    typeof window.matchMedia !== "function" ||
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * A whole number that counts up to its value when it first appears. The final value is always what
 * is in the page text; a test, a screen reader or a still-motion setting sees it at once.
 */
export function CountUp({ value, duration = 900 }: { value: number; duration?: number }) {
  const [shown, setShown] = useState(() => (prefersStill() ? value : 0));
  const from = useRef(shown);

  useEffect(() => {
    const start = from.current;
    const still = prefersStill();
    const began = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = still ? 1 : Math.min(1, (now - began) / duration);
      const next = Math.round(start + (value - start) * (1 - Math.pow(1 - t, 3)));
      from.current = next;
      setShown(next);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, duration]);

  return <>{shown}</>;
}

/** A heartbeat trace that draws itself across, then keeps travelling. Purely decorative. */
export function PulseLine({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`pulse-line ${className}`.trim()}
      viewBox="0 0 640 90"
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        className="pulse-base"
        d="M0 52 H110 L128 52 L142 30 L158 74 L176 8 L196 82 L212 52 H300 L316 52 L328 38 L342 60 L356 52 H460 L478 52 L492 24 L508 78 L526 14 L546 70 L562 52 H640"
      />
      <path
        className="pulse-trace"
        pathLength={1}
        d="M0 52 H110 L128 52 L142 30 L158 74 L176 8 L196 82 L212 52 H300 L316 52 L328 38 L342 60 L356 52 H460 L478 52 L492 24 L508 78 L526 14 L546 70 L562 52 H640"
      />
    </svg>
  );
}

/** A ring that fills to a share of a whole, with the figure in the middle. */
export function Ring({
  value,
  max,
  label,
  children,
}: {
  value: number;
  max: number;
  label: string;
  children?: React.ReactNode;
}) {
  const share = max > 0 ? Math.min(1, value / max) : 0;
  return (
    <div className="ring" role="img" aria-label={label} style={{ ["--share" as string]: share }}>
      <svg viewBox="0 0 120 120" aria-hidden="true" focusable="false">
        <circle className="ring-track" cx="60" cy="60" r="52" />
        <circle className="ring-fill" cx="60" cy="60" r="52" pathLength={1} />
      </svg>
      <div className="ring-centre" aria-hidden="true">
        {children}
      </div>
    </div>
  );
}
