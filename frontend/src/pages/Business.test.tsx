import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import type { Delivery, Policy, Trends } from "../api/types";
import { resetSessionCache, setSession } from "../lib/authStore";
import { installFakeApi } from "../test/fakeApi";
import { appointment, clockInfo, doctor, renderPage } from "../test/utils";
import MyDay from "./MyDay";
import Policies from "./Policies";
import Reports from "./Reports";
import Messages from "./Messages";
import Staff from "./Staff";

beforeEach(() => {
  window.sessionStorage.clear();
  resetSessionCache();
  setSession(null);
});

const open = { "GET /auth/status": { body: { required: false, accounts: false } } };
const signedIn = {
  "GET /auth/status": { body: { required: true, accounts: true } },
};

const policy = (over: Partial<Policy> = {}): Policy => ({
  horizon_days: 60,
  late_cancel_hours: 2,
  strike_lookback_days: 30,
  strikes: 2,
  undo_minutes: 10,
  offer_hold_minutes: 30,
  reminder_first_hours: 24,
  reminder_second_hours: 2,
  defaults: {
    horizon_days: 60,
    late_cancel_hours: 2,
    strike_lookback_days: 30,
    strikes: 2,
    undo_minutes: 10,
    offer_hold_minutes: 30,
    reminder_first_hours: 24,
    reminder_second_hours: 2,
  },
  bounds: {
    horizon_days: [1, 365],
    late_cancel_hours: [0, 72],
    strike_lookback_days: [1, 180],
    strikes: [1, 10],
    undo_minutes: [0, 60],
    offer_hold_minutes: [5, 240],
    reminder_first_hours: [0, 168],
    reminder_second_hours: [0, 48],
  },
  updated_at_utc: null,
  updated_by: null,
  ...over,
});

const delivery = (over: Partial<Delivery> = {}): Delivery => ({
  gateway: null,
  channel: null,
  reminder_first_hours: 24,
  reminder_second_hours: 2,
  counts: { PENDING: 3, SENT: 1, FAILED: 0, SKIPPED: 2, reminders_sent: 1 },
  ...over,
});

describe("the clinic's rules", () => {
  it("shows each rule in words and saves only what was changed", async () => {
    const api = installFakeApi({
      ...open,
      "GET /policy": { body: policy() },
      "GET /notifications/delivery": { body: delivery() },
      "PATCH /policy": { body: policy({ late_cancel_hours: 4 }) },
    });
    const user = userEvent.setup();
    renderPage(<Policies />);

    expect(await screen.findByText(/Visits can be booked up to 60 days ahead/)).toBeInTheDocument();
    expect(
      screen.getByText(/cancels less than 2 hours before the visit has cancelled late/),
    ).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Save rules" });
    expect(save).toBeDisabled(); // nothing changed yet

    const field = screen.getByLabelText(/A cancellation counts as late when it is less than/);
    await user.clear(field);
    await user.type(field, "4");
    expect(screen.getByText(/less than 4 hours before the visit/)).toBeInTheDocument();

    await user.click(save);
    await waitFor(() => expect(api.count("PATCH", "/policy")).toBe(1));
    expect(api.last("PATCH", "/policy")?.body).toEqual({ late_cancel_hours: 4 });
    expect(await screen.findByText(/Rules saved/)).toBeInTheDocument();
  });

  it("refuses a value outside its range before asking the server", async () => {
    const api = installFakeApi({
      ...open,
      "GET /policy": { body: policy() },
      "GET /notifications/delivery": { body: delivery() },
    });
    const user = userEvent.setup();
    renderPage(<Policies />);
    const field = await screen.findByLabelText(/Bookings open up to/);
    await user.clear(field);
    await user.type(field, "999");
    expect(screen.getByText("Use a whole number from 1 to 365.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save rules" })).toBeDisabled();
    expect(api.count("PATCH", "/policy")).toBe(0);
  });

  it("offers the standard values back", async () => {
    installFakeApi({
      ...open,
      "GET /policy": { body: policy({ strikes: 4 }) },
      "GET /notifications/delivery": { body: delivery() },
    });
    const user = userEvent.setup();
    renderPage(<Policies />);
    const field = await screen.findByLabelText(/Late cancellations or no-shows that trigger it/);
    expect(field).toHaveValue(4);
    await user.click(screen.getByRole("button", { name: "Use the standard values" }));
    expect(field).toHaveValue(2);
  });

  it("explains that reminders wait for reception when no gateway is connected", async () => {
    installFakeApi({
      ...open,
      "GET /policy": { body: policy() },
      "GET /notifications/delivery": { body: delivery() },
    });
    renderPage(<Policies />);
    expect(await screen.findByText(/No message gateway is connected/)).toBeInTheDocument();
  });

  it("is read-only for a receptionist", async () => {
    setSession({ token: "t", name: "Meera", role: "RECEPTIONIST" });
    installFakeApi({
      ...signedIn,
      "GET /policy": { body: policy() },
      "GET /notifications/delivery": { body: delivery() },
    });
    renderPage(<Policies />);
    expect(
      await screen.findByText("Only an administrator can change these rules."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Bookings open up to/)).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save rules" })).not.toBeInTheDocument();
  });
});

describe("messages and reminders", () => {
  const page = { body: { items: [], total: 0, limit: 20, offset: 0 } };

  it("says how messages are sent and queues due reminders on demand", async () => {
    const api = installFakeApi({
      ...open,
      "GET /notifications": page,
      "GET /notifications/delivery": {
        body: delivery({ gateway: "twilio", channel: "whatsapp" }),
      },
      "POST /notifications/reminders/run": { body: { queued: 2 } },
    });
    const user = userEvent.setup();
    renderPage(<Messages />);
    expect(await screen.findByText("Automatically through Twilio WhatsApp.")).toBeInTheDocument();
    expect(screen.getByText("first 24 h before, second 2 h before")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Queue due reminders now" }));
    expect(await screen.findByText("2 reminders were queued.")).toBeInTheDocument();
    expect(api.count("POST", "/notifications/reminders/run")).toBe(1);
  });

  it("says plainly when reception sends everything by hand", async () => {
    installFakeApi({
      ...open,
      "GET /notifications": page,
      "GET /notifications/delivery": { body: delivery() },
    });
    renderPage(<Messages />);
    expect(await screen.findByText(/By hand: no gateway is connected/)).toBeInTheDocument();
  });
});

const day = (date: string, scheduled: number, over = {}) => ({
  date,
  scheduled,
  completed: 0,
  no_show: 0,
  cancelled: 0,
  upcoming: scheduled,
  ...over,
});

describe("the report", () => {
  const row = (over = {}) => ({
    doctor_id: 1,
    doctor_name: "Dr. Rao",
    capacity_slots: 8,
    appointments: 10,
    new_bookings: 10,
    booked: 2,
    completed: 6,
    no_show: 2,
    cancelled: 0,
    late_cancelled: 0,
    rescheduled: 0,
    checked_in: 0,
    utilisation: 0.5,
    no_show_rate: 0.25,
    freed_slots: 0,
    refilled: 0,
    refilled_via_waitlist: 0,
    recovery_rate: null,
    ...over,
  });
  const summary = (total: object) => ({
    body: {
      start: "2026-10-27",
      end: "2026-11-02",
      doctors: [row()],
      total: { ...row(), doctor_id: 0, doctor_name: "All doctors", ...total },
    },
  });
  const trends: Trends = {
    start: "2026-10-27",
    end: "2026-11-02",
    doctor_id: null,
    days: [day("2026-11-01", 3, { completed: 2, no_show: 1, upcoming: 0 }), day("2026-11-02", 5)],
    weekdays: [0, 1, 2, 3, 4, 5, 6].map((key) => ({
      key,
      scheduled: key === 0 ? 5 : 0,
      completed: key === 0 ? 3 : 0,
      no_show: key === 0 ? 2 : 0,
      no_show_rate: key === 0 ? 0.4 : null,
    })),
    hours: [{ key: 9, scheduled: 4, completed: 3, no_show: 1, no_show_rate: 0.25 }],
    reminder_effect: {
      reminded_visits: 4,
      reminded_no_shows: 0,
      other_visits: 6,
      other_no_shows: 2,
    },
  };

  it("compares the period with the one before and says what changed", async () => {
    const calls: string[] = [];
    installFakeApi({
      ...open,
      "GET /clock": { body: clockInfo() },
      "GET /doctors": { body: [doctor()] },
      "GET /reports/summary": (call) => {
        calls.push(call.query.from ?? "");
        // the earlier period is asked for second and had fewer visits and a lower no-show rate
        return call.query.from === "2026-10-27"
          ? summary({ appointments: 10, no_show_rate: 0.25 })
          : summary({ appointments: 7, no_show_rate: 0.1 });
      },
      "GET /reports/trends": { body: trends },
    });
    renderPage(<Reports />, "/reports");
    const figures = await screen.findByRole("region", { name: "The period in numbers" });
    expect(
      await within(figures).findByText("3 more visits than the 7 days before"),
    ).toBeInTheDocument();
    expect(
      within(figures).getByText("15 points higher than the 7 days before"),
    ).toBeInTheDocument();
    expect(calls).toContain("2026-10-20"); // the 7 days before 27 October
  });

  it("draws the days with a spoken summary and the same numbers as a table", async () => {
    installFakeApi({
      ...open,
      "GET /clock": { body: clockInfo() },
      "GET /doctors": { body: [doctor()] },
      "GET /reports/summary": summary({}),
      "GET /reports/trends": { body: trends },
    });
    renderPage(<Reports />, "/reports");
    expect(
      await screen.findByRole("img", { name: /8 visits over 2 days. Busiest day: 2 Nov with 5/ }),
    ).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Visits per day" });
    expect(within(table).getByRole("row", { name: /2 Nov 5 0 0 0 5/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Visits by weekday.*Monday, 40%/ })).toBeInTheDocument();
  });

  it("compares reminded patients with the rest", async () => {
    installFakeApi({
      ...open,
      "GET /clock": { body: clockInfo() },
      "GET /doctors": { body: [doctor()] },
      "GET /reports/summary": summary({}),
      "GET /reports/trends": { body: trends },
    });
    renderPage(<Reports />, "/reports");
    expect(await screen.findByText("Sent a reminder")).toBeInTheDocument();
    expect(screen.getByText("(0 of 4 visits)")).toBeInTheDocument();
    expect(screen.getByText("(2 of 6 visits)")).toBeInTheDocument();
  });

  it("asks for one doctor's pattern when a doctor is chosen", async () => {
    const api = installFakeApi({
      ...open,
      "GET /clock": { body: clockInfo() },
      "GET /doctors": { body: [doctor()] },
      "GET /reports/summary": summary({}),
      "GET /reports/trends": { body: trends },
    });
    const user = userEvent.setup();
    renderPage(<Reports />, "/reports");
    await screen.findByText("Visits each day");
    await screen.findByRole("option", { name: "Dr. Rao" });
    await user.selectOptions(screen.getByLabelText("Doctor (for the charts)"), "1");
    await waitFor(() => expect(api.last("GET", "/reports/trends")?.query.doctor_id).toBe("1"));
  });

  it("switches range with a quick button", async () => {
    const api = installFakeApi({
      ...open,
      "GET /clock": { body: clockInfo() },
      "GET /doctors": { body: [doctor()] },
      "GET /reports/summary": summary({}),
      "GET /reports/trends": { body: trends },
    });
    const user = userEvent.setup();
    renderPage(<Reports />, "/reports");
    await screen.findByText("Visits each day");
    await user.click(screen.getByRole("button", { name: "Last 30 days" }));
    await waitFor(() => expect(api.last("GET", "/reports/trends")?.query.from).toBe("2026-10-04"));
    expect(screen.getByRole("button", { name: "Last 30 days" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});

describe("a doctor's day", () => {
  const hh = (hour: number) => String(hour).padStart(2, "0");
  const visit = (id: number, hour: number, over = {}) =>
    appointment({
      id,
      doctor_id: 1,
      patient_name: `Patient ${id}`,
      start_at_utc: `2026-11-02T${hh(hour - 5)}:30:00Z`,
      end_at_utc: `2026-11-02T${hh(hour - 5)}:45:00Z`,
      start_at_ist: `2026-11-02T${hh(hour)}:00:00+05:30`,
      end_at_ist: `2026-11-02T${hh(hour)}:30:00+05:30`,
      ...over,
    });

  const routes = (rows: unknown[]) => ({
    ...signedIn,
    "GET /clock": { body: clockInfo() },
    "GET /doctors": {
      body: [doctor({ id: 1, name: "Dr. Rao" }), doctor({ id: 2, name: "Dr. Menon" })],
    },
    "GET /queue": { body: rows },
  });

  it("opens on the doctor's own day and hides the doctor picker", async () => {
    setSession({ token: "t", name: "Dr. Rao", role: "DOCTOR", doctor_id: 1 });
    const api = installFakeApi(routes([visit(1, 9, { allowed_actions: ["check-in", "cancel"] })]));
    renderPage(<MyDay />, "/my-day");
    expect(await screen.findByRole("heading", { name: "My day" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Doctor")).not.toBeInTheDocument();
    await waitFor(() => expect(api.last("GET", "/queue")?.query.doctor_id).toBe("1"));
  });

  it("lets reception choose whose day to see", async () => {
    setSession({ token: "t", name: "Meera", role: "RECEPTIONIST" });
    const api = installFakeApi(routes([]));
    const user = userEvent.setup();
    renderPage(<MyDay />, "/my-day");
    await screen.findByRole("option", { name: /Dr\. Menon/ });
    await user.selectOptions(screen.getByLabelText("Doctor"), "2");
    await waitFor(() => expect(api.last("GET", "/queue")?.query.doctor_id).toBe("2"));
  });

  it("puts the patient who has arrived first, then who is still to come, then who is done", async () => {
    setSession({ token: "t", name: "Dr. Rao", role: "DOCTOR", doctor_id: 1 });
    installFakeApi(
      routes([
        visit(1, 9, { status: "COMPLETED", allowed_actions: [] }),
        visit(2, 10, {
          checked_in_at_ist: "2026-11-02T09:50:00+05:30",
          checked_in_at_utc: "2026-11-02T04:20:00Z",
          allowed_actions: ["complete", "no-show"],
        }),
        visit(3, 11, { allowed_actions: ["check-in"] }),
      ]),
    );
    renderPage(<MyDay />, "/my-day");
    expect(await screen.findByText("Waiting for you")).toBeInTheDocument();
    expect(screen.getByText("Patient 2")).toBeInTheDocument();
    expect(screen.getByText("Later today")).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
    const figures = screen.getByRole("region", { name: "The day in numbers" });
    expect(within(figures).getByText("Waiting now").nextSibling).toHaveTextContent("1");
    expect(within(figures).getByText("Seen").nextSibling).toHaveTextContent("1");
  });

  it("marks a visit seen, sending the version the screen shows", async () => {
    setSession({ token: "t", name: "Dr. Rao", role: "DOCTOR", doctor_id: 1 });
    const api = installFakeApi({
      ...routes([
        visit(2, 10, {
          etag: "abc123",
          checked_in_at_ist: "2026-11-02T09:50:00+05:30",
          checked_in_at_utc: "2026-11-02T04:20:00Z",
          allowed_actions: ["complete", "no-show"],
        }),
      ]),
      "POST /appointments/2/complete": { body: visit(2, 10, { status: "COMPLETED" }) },
    });
    const user = userEvent.setup();
    renderPage(<MyDay />, "/my-day");
    await user.click(await screen.findByRole("button", { name: "Mark seen" }));
    await waitFor(() => expect(api.count("POST", "/appointments/2/complete")).toBe(1));
    expect(api.last("POST", "/appointments/2/complete")?.headers.get("if-match")).toBe('"abc123"');
  });

  it("explains a login that is not linked to a doctor", async () => {
    setSession({ token: "t", name: "Guest", role: "ADMIN" });
    installFakeApi({ ...routes([]), "GET /doctors": { body: [] } });
    renderPage(<MyDay />, "/my-day");
    expect(await screen.findByText(/not linked to a doctor yet/)).toBeInTheDocument();
  });
});

describe("the menu for a doctor's own login", () => {
  const base = {
    ...signedIn,
    "GET /clock": { body: clockInfo() },
    "GET /doctors": { body: [doctor()] },
    "GET /queue": { body: [] },
    "GET /appointments": { body: { items: [], total: 0, limit: 100, offset: 0 } },
    "GET /notifications/pending": { body: { count: 0 } },
  };

  it("shows only what a doctor may use and opens on their own day", async () => {
    setSession({ token: "t", name: "Dr. Rao", role: "DOCTOR", doctor_id: 1 });
    installFakeApi(base);
    renderPage(<App />, "/");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    for (const name of ["My day", "Day view", "Queue", "Patients", "Report"]) {
      expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    }
    for (const name of ["Book", "Calls", "Messages", "Doctors", "Clinic rules", "Staff"]) {
      expect(within(nav).queryByRole("link", { name })).not.toBeInTheDocument();
    }
    expect(await screen.findByRole("heading", { name: "My day" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "New booking" })).not.toBeInTheDocument();
  });

  it("shows reception the rules page and a way to change their password", async () => {
    setSession({ token: "t", name: "Meera", role: "RECEPTIONIST" });
    installFakeApi({
      ...base,
      "GET /policy": { body: policy() },
      "GET /notifications/delivery": { body: delivery() },
    });
    renderPage(<App />, "/");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Clinic rules" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Staff" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change password" })).toBeInTheDocument();
  });
});

describe("staff: doctor logins and reset codes", () => {
  const account = (over = {}) => ({
    id: 1,
    username: "meera",
    display_name: "Meera",
    role: "RECEPTIONIST",
    active: true,
    ...over,
  });

  it("creates a doctor's login tied to a doctor", async () => {
    const api = installFakeApi({
      ...open,
      "GET /doctors": { body: [doctor({ id: 1, name: "Dr. Rao" })] },
      "GET /staff": { body: [] },
      "POST /staff": { status: 201, body: account({ id: 2, role: "DOCTOR", doctor_id: 1 }) },
    });
    const user = userEvent.setup();
    renderPage(<Staff />);
    const form = await screen.findByRole("form", { name: "New staff account" });
    await user.type(within(form).getByLabelText("Username"), "dr.rao");
    await user.type(within(form).getByLabelText("Name shown in the history"), "Dr. Rao");
    await user.type(within(form).getByLabelText(/^Password/), "long-enough-pass");
    await user.selectOptions(within(form).getByLabelText("Role"), "DOCTOR");
    await user.selectOptions(await within(form).findByLabelText("Which doctor"), "1");
    await user.click(within(form).getByRole("button", { name: "Create account" }));
    expect(api.last("POST", "/staff")?.body).toEqual({
      username: "dr.rao",
      display_name: "Dr. Rao",
      password: "long-enough-pass",
      role: "DOCTOR",
      doctor_id: 1,
    });
  });

  it("issues a one-time reset code and shows it once", async () => {
    installFakeApi({
      ...open,
      "GET /doctors": { body: [] },
      "GET /staff": { body: [account()] },
      "POST /staff/1/reset-code": {
        body: { code: "K7QX-92MD", expires_at_utc: "2026-11-02T04:30:00Z" },
      },
    });
    const user = userEvent.setup();
    renderPage(<Staff />);
    await user.click(await screen.findByRole("button", { name: "Issue a reset code for meera" }));
    expect(await screen.findByText("K7QX-92MD")).toBeInTheDocument();
    expect(screen.getByText(/works once and stops working at 10:00/)).toBeInTheDocument();
  });

  it("does not offer to switch a doctor's login to another role", async () => {
    installFakeApi({
      ...open,
      "GET /doctors": { body: [doctor({ id: 1, name: "Dr. Rao" })] },
      "GET /staff": {
        body: [account({ id: 3, username: "dr.rao", role: "DOCTOR", doctor_id: 1 })],
      },
    });
    renderPage(<Staff />);
    expect(await screen.findByText(/Doctor/, { selector: "span" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Role of dr.rao")).not.toBeInTheDocument();
  });
});
