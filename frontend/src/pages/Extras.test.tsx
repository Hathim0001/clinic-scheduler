import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import type { WaitlistEntry } from "../api/types";
import { apiError, installFakeApi } from "../test/fakeApi";
import { appointment, clockInfo, doctor, flaggedDeposit, patient, renderPage } from "../test/utils";
import Admin from "./Admin";
import Book from "./Book";
import { PatientDetail } from "./Patients";

const entry = (overrides: Partial<WaitlistEntry> = {}): WaitlistEntry => ({
  id: 5,
  doctor_id: 1,
  doctor_name: "Dr. Rao",
  patient_id: 7,
  patient_name: "Kavita Nair",
  patient_phone: "+919000000001",
  date: "2026-11-02",
  status: "WAITING",
  position: 1,
  offered_start_at_utc: null,
  offered_start_at_ist: null,
  offer_expires_at_utc: null,
  offer_expires_at_ist: null,
  appointment_id: null,
  ...overrides,
});

const offered = entry({
  status: "OFFERED",
  position: null,
  offered_start_at_utc: "2026-11-02T04:30:00Z",
  offered_start_at_ist: "2026-11-02T10:00:00+05:30",
  offer_expires_at_utc: "2026-11-02T05:00:00Z",
  offer_expires_at_ist: "2026-11-02T10:30:00+05:30",
});

const empty = {
  doctor_id: 1,
  date: "2026-11-02",
  slot_length_min: 30,
  source: "WEEKLY",
  windows: [{ start: "09:00", end: "13:00" }],
  slots: [],
  unavailable_reason: null,
};

const base = () => ({
  "GET /clock": { body: clockInfo() },
  "GET /doctors": { body: [doctor()] },
});

describe("the waitlist", () => {
  it("offers to join when a day has no free time, and says what place the patient got", async () => {
    const api = installFakeApi({
      ...base(),
      "GET /patients/7": { body: patient() },
      "GET /doctors/1/slots": { body: empty },
      "POST /doctors/1/waitlist": { status: 201, body: entry({ position: 3 }) },
    });
    const user = userEvent.setup();
    renderPage(<Book />, "/book?patient=7&doctor=1&date=2026-11-02");

    await user.click(await screen.findByRole("button", { name: /Join the waitlist/ }));

    expect(await screen.findByText(/is number 3 in the queue/)).toBeInTheDocument();
    expect(api.last("POST", "/doctors/1/waitlist")?.body).toEqual({
      patient_id: 7,
      date: "2026-11-02",
    });
  });

  it("shows an open offer on the patient page and books it with a reason", async () => {
    const api = installFakeApi({
      ...base(),
      "GET /patients/7": { body: patient() },
      "GET /patients/7/waitlist": { body: [offered] },
      "GET /patients/7/appointments": { body: { items: [], total: 0, limit: 50, offset: 0 } },
      "POST /waitlist/5/accept": {
        body: { entry: entry({ status: "BOOKED" }), appointment: appointment() },
      },
    });
    const user = userEvent.setup();
    renderPage(
      <Routes>
        <Route path="/patients/:id" element={<PatientDetail />} />
      </Routes>,
      "/patients/7",
    );

    const accept = await screen.findByRole("button", { name: "Accept and book" });
    expect(accept).toBeDisabled(); // a reason is needed first
    await user.type(screen.getByLabelText("Reason for the visit"), "Fever");
    await user.click(accept);

    await waitFor(() => expect(api.count("POST", "/waitlist/5/accept")).toBe(1));
    expect(api.last("POST", "/waitlist/5/accept")?.body).toEqual({
      reason: "Fever",
      deposit_confirmed: false,
    });
  });

  it("asks a flagged patient to acknowledge the deposit before accepting", async () => {
    installFakeApi({
      ...base(),
      "GET /patients/7": {
        body: patient({ deposit_required: true, deposit: flaggedDeposit }),
      },
      "GET /patients/7/waitlist": { body: [offered] },
      "GET /patients/7/appointments": { body: { items: [], total: 0, limit: 50, offset: 0 } },
    });
    const user = userEvent.setup();
    renderPage(
      <Routes>
        <Route path="/patients/:id" element={<PatientDetail />} />
      </Routes>,
      "/patients/7",
    );

    await user.type(await screen.findByLabelText("Reason for the visit"), "Fever");
    const accept = screen.getByRole("button", { name: "Accept and book" });
    expect(accept).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    expect(accept).toBeEnabled();
  });

  it("lets a waiting patient leave the queue", async () => {
    const api = installFakeApi({
      ...base(),
      "GET /patients/7": { body: patient() },
      "GET /patients/7/waitlist": { body: [entry()] },
      "GET /patients/7/appointments": { body: { items: [], total: 0, limit: 50, offset: 0 } },
      "DELETE /waitlist/5": { body: entry({ status: "CANCELLED" }) },
    });
    const user = userEvent.setup();
    renderPage(
      <Routes>
        <Route path="/patients/:id" element={<PatientDetail />} />
      </Routes>,
      "/patients/7",
    );

    expect(await screen.findByText(/number 1 in the queue/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Leave the waitlist" }));
    await waitFor(() => expect(api.count("DELETE", "/waitlist/5")).toBe(1));
  });
});

describe("repeat bookings", () => {
  it("books a series through the recurring endpoint", async () => {
    const slot = {
      start_at_utc: "2026-11-02T04:30:00Z",
      start_at_ist: "2026-11-02T10:00:00+05:30",
      end_at_utc: "2026-11-02T05:00:00Z",
      end_at_ist: "2026-11-02T10:30:00+05:30",
    };
    const api = installFakeApi({
      ...base(),
      "GET /patients/7": { body: patient() },
      "GET /doctors/1/slots": { body: { ...empty, slots: [slot] } },
      "POST /appointments/recurring": { status: 201, body: { appointments: [appointment()] } },
    });
    const user = userEvent.setup();
    renderPage(<Book />, "/book?patient=7&doctor=1&date=2026-11-02");

    await user.click(await screen.findByRole("button", { name: "10:00–10:30" }));
    await user.type(screen.getByLabelText("Reason"), "Physio");
    await user.click(screen.getByLabelText("Repeat this appointment"));
    await user.click(screen.getByRole("button", { name: "Book the appointment" }));

    await waitFor(() => expect(api.count("POST", "/appointments/recurring")).toBe(1));
    expect(api.last("POST", "/appointments/recurring")?.body).toMatchObject({
      every_days: 7,
      count: 4,
      reason: "Physio",
    });
    expect(api.count("POST", "/appointments")).toBe(0);
  });
});

describe("adding and removing doctors", () => {
  const routes = (extra = {}) => ({
    ...base(),
    "GET /doctors/1/weekly-windows": { body: { windows: [], needs_attention: [] } },
    "GET /doctors/1/overrides": { body: [] },
    "GET /appointments": { body: { items: [], total: 0, limit: 100, offset: 0 } },
    ...extra,
  });

  it("creates a doctor from the form", async () => {
    const api = installFakeApi(
      routes({ "POST /doctors": { status: 201, body: doctor({ id: 2, name: "Dr. New" }) } }),
    );
    const user = userEvent.setup();
    renderPage(<Admin />, "/admin");

    await user.type(await screen.findByLabelText("New doctor name"), "Dr. New");
    await user.type(screen.getByLabelText("New doctor speciality"), "ENT");
    await user.click(screen.getByRole("button", { name: "Add doctor" }));

    await waitFor(() => expect(api.count("POST", "/doctors")).toBe(1));
    expect(api.last("POST", "/doctors")?.body).toEqual({
      name: "Dr. New",
      speciality: "ENT",
      daily_cap: 10,
      slot_length_min: 30,
    });
  });

  it("asks before removing a doctor and shows the server's refusal", async () => {
    const api = installFakeApi(
      routes({
        "DELETE /doctors/1": apiError(
          409,
          "DOCTOR_HAS_APPOINTMENTS",
          "Dr. Rao has 3 appointment(s) on record, so cannot be deleted.",
        ),
      }),
    );
    const user = userEvent.setup();
    renderPage(<Admin />, "/admin");

    await user.click(await screen.findByRole("button", { name: /^Remove Dr\. Rao/ }));
    expect(api.count("DELETE", "/doctors/1")).toBe(0); // not yet: it asks first
    await user.click(screen.getByRole("button", { name: /^Yes, remove/ }));

    expect(await screen.findByText(/cannot be deleted/)).toBeInTheDocument();
  });
});
