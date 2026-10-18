import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import type { SlotsResponse } from "../api/types";
import { PatientPicker } from "../components/PatientPicker";
import { apiError, installFakeApi } from "../test/fakeApi";
import { appointment, clockInfo, doctor, patient, renderPage } from "../test/utils";
import Book from "./Book";
import { PatientDetail } from "./Patients";

const slot = (start: string, end: string) => ({
  start_at_utc: "2026-11-02T04:30:00Z",
  start_at_ist: `2026-11-02T${start}:00+05:30`,
  end_at_utc: "2026-11-02T05:30:00Z",
  end_at_ist: `2026-11-02T${end}:00+05:30`,
});

const slotsFor = (durationMin: number): SlotsResponse => ({
  doctor_id: 1,
  date: "2026-11-02",
  slot_length_min: 30,
  source: "WEEKLY",
  windows: [{ start: "09:00", end: "13:00" }],
  slots: [slot("10:00", durationMin === 60 ? "11:00" : "10:30")],
  unavailable_reason: null,
  duration_min: durationMin,
});

const base = () => ({
  "GET /clock": { body: clockInfo() },
  "GET /doctors": { body: [doctor()] },
  "GET /patients/7": { body: patient() },
  "POST /triage": { body: { urgent: false, message: null } },
});

describe("visits of several slots", () => {
  it("offers the lengths in minutes, asks for times that fit, and books that length", async () => {
    const api = installFakeApi({
      ...base(),
      "GET /doctors/1/slots": (call) => ({
        body: slotsFor(Number(call.query.slots) === 2 ? 60 : 30),
      }),
      "POST /appointments": {
        status: 201,
        body: appointment({ slots: 2, duration_min: 60, end_at_ist: "2026-11-02T11:00:00+05:30" }),
      },
    });
    const user = userEvent.setup();
    renderPage(<Book />, "/book?patient=7&doctor=1&date=2026-11-02");

    const length = await screen.findByLabelText("Length of the visit");
    expect(
      within(length)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual([
      "30 minutes",
      "60 minutes (2 slots)",
      "90 minutes (3 slots)",
      "120 minutes (4 slots)",
    ]);
    await user.selectOptions(length, "2");

    expect(await screen.findByRole("button", { name: "10:00–11:00" })).toBeInTheDocument();
    expect(api.last("GET", "/doctors/1/slots")?.query.slots).toBe("2");

    await user.click(screen.getByRole("button", { name: "10:00–11:00" }));
    await user.type(screen.getByLabelText("Reason"), "Physio");
    await user.click(screen.getByRole("button", { name: "Book the appointment" }));
    await waitFor(() => expect(api.count("POST", "/appointments")).toBe(1));
    expect(api.last("POST", "/appointments")?.body).toMatchObject({ slots: 2, reason: "Physio" });
  });

  it("uses a new idempotency key when only the length changes", async () => {
    const api = installFakeApi({
      ...base(),
      "GET /doctors/1/slots": () => ({ body: slotsFor(30) }),
      "POST /appointments": apiError(503, "SERVICE_UNAVAILABLE", "busy"),
    });
    const user = userEvent.setup();
    renderPage(<Book />, "/book?patient=7&doctor=1&date=2026-11-02");
    await user.click(await screen.findByRole("button", { name: "10:00–10:30" }));
    await user.type(screen.getByLabelText("Reason"), "Fever");
    await user.click(screen.getByRole("button", { name: "Book the appointment" }));
    await waitFor(() => expect(api.count("POST", "/appointments")).toBe(1));
    await user.click(screen.getByRole("button", { name: "Book the appointment" }));
    await waitFor(() => expect(api.count("POST", "/appointments")).toBe(2));
    const keys = api.calls
      .filter((c) => c.method === "POST" && c.path === "/appointments")
      .map((c) => c.headers.get("Idempotency-Key"));
    expect(keys[1]).toBe(keys[0]); // the same booking: the same key
  });
});

describe("moving an appointment", () => {
  const rescheduleRoutes = (extra = {}) => ({
    ...base(),
    "GET /appointments/41": { body: appointment() },
    "GET /doctors/1/slots": () => ({ body: slotsFor(30) }),
    ...extra,
  });

  const late = apiError(
    409,
    "LATE_RESCHEDULE_NEEDS_CONFIRMATION",
    "This appointment starts in 90 minutes, so moving it now is recorded as a late cancellation.",
    { minutes_until_start: 90 },
  );

  it("asks before recording a late cancellation, then goes ahead when told to", async () => {
    let attempts = 0;
    const api = installFakeApi(
      rescheduleRoutes({
        "POST /appointments/41/reschedule": (call: { body: unknown }) => {
          attempts += 1;
          return (call.body as { acknowledge_late?: boolean }).acknowledge_late
            ? {
                body: {
                  old: appointment({ status: "LATE_CANCELLED" }),
                  new: appointment({ id: 42 }),
                },
              }
            : late;
        },
      }),
    );
    const user = userEvent.setup();
    renderPage(<Book />, "/book?reschedule=41");
    await user.click(await screen.findByRole("button", { name: "10:00–10:30" }));
    await user.click(screen.getByRole("button", { name: "Move the appointment" }));

    expect(await screen.findByText(/starts in 90 minutes/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); // a question, not an error
    await user.click(screen.getByRole("button", { name: "Move it anyway (late cancellation)" }));

    await waitFor(() => expect(attempts).toBe(2));
    expect(
      api.calls.filter((c) => c.path === "/appointments/41/reschedule")[1]?.body,
    ).toMatchObject({
      by: "PATIENT",
      acknowledge_late: true,
    });
  });

  it("lets the clinic make the move instead, which needs no confirmation", async () => {
    const api = installFakeApi(
      rescheduleRoutes({
        "POST /appointments/41/reschedule": (call: { body: unknown }) =>
          (call.body as { by?: string }).by === "CLINIC"
            ? { body: { old: appointment({ status: "CANCELLED" }), new: appointment({ id: 42 }) } }
            : late,
      }),
    );
    const user = userEvent.setup();
    renderPage(<Book />, "/book?reschedule=41");
    await user.click(await screen.findByRole("button", { name: "10:00–10:30" }));
    await user.click(screen.getByRole("button", { name: "Move the appointment" }));
    await user.click(await screen.findByRole("button", { name: "Have the clinic make the move" }));
    expect(screen.getByRole("radio", { name: /^The clinic/ })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Move the appointment" }));
    await waitFor(() => expect(api.count("POST", "/appointments/41/reschedule")).toBe(2));
    expect(api.last("POST", "/appointments/41/reschedule")?.body).toMatchObject({ by: "CLINIC" });
    expect(await screen.findByText(/Booked:/)).toBeInTheDocument();
  });

  it("says so when the visit does not fit the chosen doctor's slots", async () => {
    installFakeApi(
      rescheduleRoutes({
        "GET /appointments/41": { body: appointment({ duration_min: 45, slots: 3 }) },
      }),
    );
    renderPage(<Book />, "/book?reschedule=41");
    expect(await screen.findByText(/lasts 45 minutes, which does not fit/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move the appointment" })).toBeDisabled();
  });

  it("keeps the visit's length in slots for a doctor whose slots divide it", async () => {
    const api = installFakeApi(
      rescheduleRoutes({
        "GET /appointments/41": { body: appointment({ duration_min: 60, slots: 2 }) },
        "GET /doctors/1/slots": () => ({ body: slotsFor(60) }),
      }),
    );
    renderPage(<Book />, "/book?reschedule=41");
    expect(await screen.findByRole("button", { name: "10:00–11:00" })).toBeInTheDocument();
    expect(api.last("GET", "/doctors/1/slots")?.query.slots).toBe("2");
    expect(screen.queryByLabelText("Length of the visit")).not.toBeInTheDocument();
  });
});

describe("a number that several patients share", () => {
  const owner = { patient_id: 3, name: "Asha Iyer", date_of_birth: "1985-04-02" };
  const taken = apiError(
    409,
    "PHONE_TAKEN",
    "This phone number is already registered to Asha Iyer.",
    {
      patient_id: 3,
      patients: [owner],
    },
  );

  async function fillNewPatient(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("button", { name: "New patient" }));
    const form = screen.getByRole("form", { name: "New patient" });
    await user.type(within(form).getByLabelText("Name"), "Child One");
    await user.type(within(form).getByLabelText("Phone"), "9876543210");
    await user.type(within(form).getByLabelText("Date of birth"), "2012-04-04");
    await user.click(within(form).getByRole("button", { name: "Register patient" }));
  }

  it("lets the person pick the existing patient instead", async () => {
    installFakeApi({
      ...base(),
      "GET /patients": { body: { items: [], total: 0, limit: 10, offset: 0 } },
      "POST /patients": taken,
    });
    const user = userEvent.setup();
    let chosen: number | null = null;
    renderPage(<PatientPicker onSelect={(p) => (chosen = p.id)} />);
    await fillNewPatient(user);
    await user.click(await screen.findByRole("button", { name: "Use Asha Iyer" }));
    expect(chosen).toBe(3);
  });

  it("registers a family member on the number only when told to", async () => {
    const api = installFakeApi({
      ...base(),
      "GET /patients": { body: { items: [], total: 0, limit: 10, offset: 0 } },
      "POST /patients": (call: { body: unknown }) =>
        (call.body as { shares_phone?: boolean }).shares_phone
          ? { status: 201, body: patient({ id: 9, name: "Child One" }) }
          : taken,
    });
    const user = userEvent.setup();
    let chosen: number | null = null;
    renderPage(<PatientPicker onSelect={(p) => (chosen = p.id)} />);
    await fillNewPatient(user);
    expect(api.count("POST", "/patients")).toBe(1);
    await user.click(
      await screen.findByRole("button", { name: "Register as a family member on this number" }),
    );
    await waitFor(() => expect(chosen).toBe(9));
    expect(api.last("POST", "/patients")?.body).toMatchObject({ shares_phone: true });
  });

  it("asks the same when a patient's phone is edited onto a number in use", async () => {
    const api = installFakeApi({
      ...base(),
      "GET /patients/7/waitlist": { body: [] },
      "GET /patients/7/appointments": { body: { items: [], total: 0, limit: 50, offset: 0 } },
      "PATCH /patients/7": (call: { body: unknown }) =>
        (call.body as { shares_phone?: boolean }).shares_phone
          ? { body: patient({ phone: "+919876543210" }) }
          : taken,
    });
    const user = userEvent.setup();
    renderPage(
      <Routes>
        <Route path="/patients/:id" element={<PatientDetail />} />
      </Routes>,
      "/patients/7",
    );
    const phone = await screen.findByLabelText("Phone", { selector: "input" });
    await user.clear(phone);
    await user.type(phone, "9876543210");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await user.click(await screen.findByRole("button", { name: "save it on this number anyway" }));
    await waitFor(() => expect(api.count("PATCH", "/patients/7")).toBe(2));
    expect(api.last("PATCH", "/patients/7")?.body).toMatchObject({ shares_phone: true });
  });
});
