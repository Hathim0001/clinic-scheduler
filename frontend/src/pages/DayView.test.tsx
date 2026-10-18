import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";
import type { ScheduleResponse, ScheduleSlot } from "../api/types";
import { installFakeApi } from "../test/fakeApi";
import { appointment, clockInfo, doctor, renderPage } from "../test/utils";
import DayView from "./DayView";

const cell = (
  start: string,
  end: string,
  state: ScheduleSlot["state"],
  booked: ScheduleSlot["appointment"] = null,
): ScheduleSlot => ({
  start_at_utc: `2026-11-02T${start}:00Z`,
  start_at_ist: `2026-11-02T${start}:00+05:30`,
  end_at_utc: `2026-11-02T${end}:00Z`,
  end_at_ist: `2026-11-02T${end}:00+05:30`,
  state,
  appointment: booked,
});

const booked = appointment({ id: 41, patient_name: "Kavita Nair" });

const schedule: ScheduleResponse = {
  doctor_id: 1,
  date: "2026-11-02",
  slot_length_min: 30,
  source: "WEEKLY",
  windows: [{ start: "09:00", end: "13:00" }],
  slots: [
    cell("09:00", "09:30", "PAST"),
    cell("10:00", "10:30", "BOOKED", booked),
    cell("10:30", "11:00", "FREE"),
    cell("11:00", "11:30", "CAPPED"),
  ],
  outside_availability: [],
  unavailable_reason: null,
};

const routes = (extra = {}) => ({
  "GET /clock": { body: clockInfo() },
  "GET /doctors": { body: [doctor()] },
  "GET /doctors/1/schedule": { body: schedule },
  ...extra,
});

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search}</p>;
}

const page = (
  <>
    <Routes>
      <Route path="/day" element={<DayView />} />
      <Route path="/book" element={<p>the booking page</p>} />
    </Routes>
    <Where />
  </>
);
const link = "/day?doctor=1&date=2026-11-02";

describe("day view", () => {
  it("labels every slot with its state in words, never colour alone", async () => {
    installFakeApi(routes());
    renderPage(page, link);
    expect(await screen.findByText("Kavita Nair")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /09:00–09:30\s*Past/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /10:30–11:00\s*Free: click to book/ })).toBeEnabled();
    expect(
      screen.getByRole("button", { name: /11:00–11:30\s*Daily limit reached/ }),
    ).toBeDisabled();
    expect(screen.getByText("09:00–13:00 IST")).toBeInTheDocument();
  });

  it("starts a booking, prefilled, from a free slot", async () => {
    installFakeApi(routes());
    const user = userEvent.setup();
    renderPage(page, link);

    await user.click(await screen.findByRole("button", { name: /10:30–11:00/ }));

    expect(await screen.findByText("the booking page")).toBeInTheDocument();
    const where = screen.getByTestId("where").textContent ?? "";
    expect(where).toContain("/book?doctor=1&date=2026-11-02&start=");
    expect(decodeURIComponent(where)).toContain("start=2026-11-02T10:30:00+05:30");
  });

  it("shows the details and the allowed actions of a booked slot", async () => {
    const api = installFakeApi(routes({ "GET /appointments/41": { body: booked } }));
    const user = userEvent.setup();
    renderPage(page, link);

    await user.click(await screen.findByRole("button", { name: /10:00–10:30/ }));

    expect(await screen.findByRole("article", { name: "Appointment 41" })).toBeInTheDocument();
    expect(screen.getByText("Fever, 3 days")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reschedule" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Complete" })).toBeDisabled();
    await waitFor(() => expect(api.count("GET", "/appointments/41")).toBe(1));
  });

  it("explains a day without slots using the reason from the server", async () => {
    installFakeApi(
      routes({
        "GET /doctors/1/schedule": {
          body: {
            ...schedule,
            slots: [],
            windows: [],
            source: "OVERRIDE",
            unavailable_reason: "NO_AVAILABILITY",
          },
        },
      }),
    );
    renderPage(page, link);
    expect(await screen.findByText(/The doctor is not working on this date/)).toBeInTheDocument();
    expect(
      screen.getByText(/a leave day or special hours were set for this date/),
    ).toBeInTheDocument();
  });

  it("lists bookings that fall outside the doctor's hours under their own heading", async () => {
    const orphan = appointment({ id: 50, patient_name: "Rahul Verma", needs_attention: true });
    installFakeApi(
      routes({
        "GET /doctors/1/schedule": {
          body: {
            ...schedule,
            slots: [],
            unavailable_reason: "NO_AVAILABILITY",
            outside_availability: [orphan],
          },
        },
      }),
    );
    renderPage(page, link);
    expect(
      await screen.findByRole("heading", { name: /Booked outside the doctor's hours/ }),
    ).toBeInTheDocument();
    const card = screen.getByRole("article", { name: "Appointment 50" });
    expect(card).toHaveTextContent("Needs attention");
    expect(card).toHaveTextContent("Move it or cancel it");
  });

  it("moves to the next day and back through the address", async () => {
    const api = installFakeApi(routes());
    const user = userEvent.setup();
    renderPage(page, link);
    await screen.findByText("Kavita Nair");

    await user.click(screen.getByRole("button", { name: "Next day" }));

    await waitFor(() =>
      expect(api.last("GET", "/doctors/1/schedule")?.query.date).toBe("2026-11-03"),
    );
    expect(screen.getByTestId("where")).toHaveTextContent("date=2026-11-03");
  });

  it("offers a retry when the server is busy", async () => {
    installFakeApi(
      routes({
        "GET /doctors/1/schedule": {
          status: 503,
          body: {
            error: { code: "SERVICE_UNAVAILABLE", message: "busy", details: {}, request_id: "r1" },
          },
        },
      }),
    );
    renderPage(page, link);
    expect(await screen.findByRole("alert")).toHaveTextContent("The server is busy or waking up");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
