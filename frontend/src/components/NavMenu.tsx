import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router";

interface Props {
  label: string;
  /** Link paths inside the menu: the button looks current when the page is one of them. */
  paths: string[];
  /** How many things inside need attention; shown on the button so it is not hidden by the menu. */
  badge?: number;
  badgeLabel?: string;
  children: ReactNode;
}

/**
 * A disclosure menu for the links that are used now and then, so the bar keeps the five that are
 * used all day. It is a plain button that shows a list of links: Escape or a click outside closes it
 * and Escape hands focus back to the button, so a keyboard user is never left inside a hidden list.
 */
export function NavMenu({ label, paths, badge = 0, badgeLabel, children }: Props) {
  const { pathname } = useLocation();
  // Open for one page only: moving to another page closes the menu without an effect.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const setOpen = (next: boolean | ((o: boolean) => boolean)) => {
    const value = typeof next === "function" ? next(open) : next;
    setOpenOn(value ? pathname : null);
  };
  const listId = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpenOn(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenOn(null);
        button.current?.focus();
      }
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const current = paths.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  return (
    <div className="nav-menu" ref={root}>
      <button
        ref={button}
        type="button"
        className="nav-menu-button"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-current={current ? "page" : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        {label}
        {badge > 0 && (
          <span className="badge-attention" aria-label={badgeLabel ?? `${badge} waiting`}>
            {badge}
          </span>
        )}
        <svg className="nav-menu-chevron" viewBox="0 0 10 6" aria-hidden="true" focusable="false">
          <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </button>
      {open && (
        <ul id={listId} className="nav-menu-list">
          {children}
        </ul>
      )}
    </div>
  );
}
