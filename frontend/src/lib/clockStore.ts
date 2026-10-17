// The test clock the reviewer chose is kept in localStorage, so a page reload keeps it. Storage can
// be unavailable (private windows, blocked site data), so every access is wrapped.

const KEY = "clinic.testClock";

export function loadTestClock(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function saveTestClock(value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, value);
  } catch {
    // keep working without persistence
  }
}
