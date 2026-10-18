// Every time on screen is India Standard Time and says so. The server sends `..._ist` strings; these
// helpers only decide how to write them. IST has no daylight saving, so a plain +05:30 is exact.

const ZONE = "Asia/Kolkata";

const parts = (iso: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormatPart[] =>
  new Intl.DateTimeFormat("en-IN", { timeZone: ZONE, hour12: false, ...options }).formatToParts(
    new Date(iso),
  );

const pick = (found: Intl.DateTimeFormatPart[], type: string): string =>
  found.find((part) => part.type === type)?.value ?? "";

/** 2 Nov 2026, 10:00 IST */
export function formatIST(iso: string): string {
  const p = parts(iso, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${pick(p, "day")} ${pick(p, "month")} ${pick(p, "year")}, ${pick(p, "hour")}:${pick(p, "minute")} IST`;
}

/** 10:00 (24-hour clock, India) */
export function formatTimeIST(iso: string): string {
  const p = parts(iso, { hour: "2-digit", minute: "2-digit" });
  return `${pick(p, "hour")}:${pick(p, "minute")}`;
}

/** Mon 2 Nov 2026 */
export function formatDayIST(iso: string): string {
  const p = parts(iso, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  return `${pick(p, "weekday")} ${pick(p, "day")} ${pick(p, "month")} ${pick(p, "year")}`;
}

/** 2026-11-02, the India calendar date of an instant */
export function istDate(iso: string): string {
  const p = parts(iso, { year: "numeric", month: "2-digit", day: "2-digit" });
  return `${pick(p, "year")}-${pick(p, "month")}-${pick(p, "day")}`;
}

/** 2026-11-02T10:00, the value of a datetime-local input showing India time */
export function istInputValue(iso: string): string {
  return `${istDate(iso)}T${formatTimeIST(iso)}`;
}

/** A datetime-local value typed as India time, as the header the API wants: ...T10:00:00+05:30 */
export function istInputToIso(value: string): string {
  return `${value}:00+05:30`;
}

/** Inverse of istInputToIso for a stored header value. */
export function isoToIstInput(iso: string): string {
  return iso.slice(0, 16);
}

/** The date a given number of days after an India date (both as YYYY-MM-DD). */
/** Is someone born on `born` (YYYY-MM-DD) under 18 on the India date `today`? */
export function isChild(born: string, today: string): boolean {
  const [by = 0, bm = 0, bd = 0] = born.split("-").map(Number);
  const [ty = 0, tm = 0, td = 0] = today.split("-").map(Number);
  const birthdayPassed = tm > bm || (tm === bm && td >= bd);
  return ty - by - (birthdayPassed ? 0 : 1) < 18;
}

export function addDays(date: string, days: number): string {
  const moment = new Date(`${date}T00:00:00Z`);
  moment.setUTCDate(moment.getUTCDate() + days);
  return moment.toISOString().slice(0, 10);
}
