import { describe, expect, it } from "vitest";
import {
  addDays,
  formatDayIST,
  formatIST,
  formatTimeIST,
  isoToIstInput,
  istDate,
  istInputToIso,
  istInputValue,
} from "./formatIST";

describe("India time formatting", () => {
  it("writes an instant as India time and says so", () => {
    expect(formatIST("2026-11-02T04:30:00Z")).toBe("2 Nov 2026, 10:00 IST");
    expect(formatIST("2026-11-02T10:00:00+05:30")).toBe("2 Nov 2026, 10:00 IST");
  });

  it("uses a 24-hour clock with a leading zero", () => {
    expect(formatTimeIST("2026-11-02T03:30:00Z")).toBe("09:00");
    expect(formatTimeIST("2026-11-02T18:15:00Z")).toBe("23:45");
  });

  it("names the weekday", () => {
    expect(formatDayIST("2026-11-02T12:00:00+05:30")).toBe("Mon 2 Nov 2026");
  });

  it("takes the date from India, not from UTC", () => {
    // 19:00 UTC on 31 October is already 1 November, half past midnight, in India.
    expect(istDate("2026-10-31T19:00:00Z")).toBe("2026-11-01");
    expect(istDate("2026-10-31T18:29:59Z")).toBe("2026-10-31");
  });

  it("converts to and from the value of a datetime-local input", () => {
    expect(istInputValue("2026-11-02T04:30:00Z")).toBe("2026-11-02T10:00");
    expect(istInputToIso("2026-11-02T10:00")).toBe("2026-11-02T10:00:00+05:30");
    expect(isoToIstInput("2026-11-02T10:00:00+05:30")).toBe("2026-11-02T10:00");
  });
});

describe("adding days to a date", () => {
  it.each([
    ["2026-10-31", 1, "2026-11-01"],
    ["2026-12-31", 1, "2027-01-01"],
    ["2028-02-28", 1, "2028-02-29"],
    ["2027-02-28", 1, "2027-03-01"],
    ["2026-11-02", -2, "2026-10-31"],
    ["2026-11-02", 89, "2027-01-30"],
  ])("%s plus %i days is %s", (date, days, expected) => {
    expect(addDays(date, days)).toBe(expected);
  });
});
