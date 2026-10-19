import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "../App";
import type { ScheduleResponse } from "../api/types";
import { installFakeApi } from "../test/fakeApi";
import { appointment, clockInfo, doctor, renderPage } from "../test/utils";

const cell = (start: string, state: "BOOKED" | "FREE") => ({
  start_at_utc: `2026-11-02T${start}:00Z`,
  start_at_ist: `2026-11-02T${start}:00+05:30`,
  end_at_utc: `2026-11-02T${start}:30Z`,
  end_at_ist: `2026-11-02T${start}:30+05:30`,
  state,
  appointment: null,
});

const schedule: ScheduleResponse = {
  doctor_id: 1,
  date: "2026-11-02",
  slot_length_min: 30,
  source: "WEEKLY",
  windows: [{ start: "09:00", end: "13:00" }],
  slots: [
    cell("09:00", "BOOKED"),
    cell("09:30", "FREE"),
    cell("10:00", "FREE"),
    cell("10:30", "BOOKED"),
  ],
  outside_availability: [],
  unavailable_reason: null,
};

const done = appointment({
  id: 1,
  patient_name: "Meera Iyer",
  status: "COMPLETED",
  start_at_utc: "2026-11-02T03:00:00Z",
  end_at_utc: "2026-11-02T03:30:00Z",
  start_at_ist: "2026-11-02T08:30:00+05:30",
  end_at_ist: "2026-11-02T09:00:00+05:30",
});
const later = appointment({
  id: 2,
  patient_name: "Neha Joshi",
  start_at_utc: "2026-11-02T05:30:00Z",
  end_at_utc: "2026-11-02T06:00:00Z",
  start_at_ist: "2026-11-02T11:00:00+05:30",
  end_at_ist: "2026-11-02T11:30:00+05:30",
  checked_in_at_ist: "2026-11-02T10:50:00+05:30",
  checked_in_at_utc: "2026-11-02T05:20:00Z",
});
const missed = appointment({ id: 3, patient_name: "Rahul Verma", status: "NO_SHOW" });

const routes = (extra = {}) => ({
  "GET /clock": { body: clockInfo() },
  "GET /auth/status": { body: { required: false, accounts: false } },
  "GET /doctors": { body: [doctor()] },
  "GET /doctors/1/schedule": { body: schedule },
  "GET /queue": { body: [done, later, missed] },
  "GET /appointments": { body: { items: [], total: 0, limit: 100, offset: 0 } },
  "GET /notifications/pending": { body: { count: 0 } },
  ...extra,
});

describe("the overview", () => {
  it("shows how the day is going and who is next", async () => {
    installFakeApi(routes());
    renderPage(<App />);

    const figures = await screen.findByRole("region", { name: "Today in numbers" });
    await within(figures).findByText("Visits today");
    expect(within(figures).getByText("3")).toBeInTheDocument();
    expect(within(figures).getAllByText("1").length).toBeGreaterThanOrEqual(3);

    const next = screen.getByRole("region", { name: "Up next" });
    expect(within(next).getByRole("link", { name: "Neha Joshi" })).toBeInTheDocument();
    expect(within(next).getByText("Arrived")).toBeInTheDocument();
    expect(within(next).queryByText("Meera Iyer")).not.toBeInTheDocument();
  });

  it("shows each doctor's load and the next free time", async () => {
    installFakeApi(routes());
    renderPage(<App />);

    const load = await screen.findByRole("region", { name: "Doctors today" });
    expect(
      await within(load).findByText(
        (_, element) =>
          element?.tagName === "SPAN" && element.textContent === "2 of 4 slots booked",
      ),
    ).toBeInTheDocument();
    expect(within(load).getByRole("link", { name: "Next free 09:30" })).toBeInTheDocument();
    expect(within(load).getByRole("meter")).toHaveAttribute("aria-valuenow", "2");
  });

  it("says when nothing is waiting, and lists what is when something is", async () => {
    installFakeApi(routes());
    const { unmount } = renderPage(<App />);
    expect(await screen.findByText(/All clear/)).toBeInTheDocument();
    unmount();

    installFakeApi(routes({ "GET /notifications/pending": { body: { count: 3 } } }));
    renderPage(<App />);
    expect(
      await screen.findByRole("link", { name: /3 messages waiting to be sent/ }),
    ).toBeInTheDocument();
  });
});

describe("the navigation", () => {
  it("groups the pages and marks the one you are on", async () => {
    installFakeApi(routes());
    renderPage(<App />);

    const nav = await screen.findByRole("navigation", { name: "Main" });
    for (const name of [
      "Overview",
      "Day view",
      "Book",
      "Queue",
      "Patients",
      "Calls",
      "Messages",
      "Report",
      "Doctors",
    ]) {
      expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    }
    expect(within(nav).getByRole("link", { name: "Overview" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav).getByRole("link", { name: "Day view" })).not.toHaveAttribute("aria-current");
  });

  it("opens and closes the menu on a phone", async () => {
    const user = userEvent.setup();
    installFakeApi(routes());
    renderPage(<App />);

    const button = await screen.findByRole("button", { name: "Menu" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("closes the menu after choosing a page", async () => {
    const user = userEvent.setup();
    installFakeApi(routes());
    renderPage(<App />);

    const button = await screen.findByRole("button", { name: "Menu" });
    await user.click(button);
    await user.click(screen.getByRole("link", { name: "Queue" }));
    expect(await screen.findByRole("heading", { name: "Today's queue" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
  });
});
