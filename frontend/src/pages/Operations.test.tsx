import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import type { DoctorReport, WaitlistEntry } from "../api/types";
import { AppointmentCard } from "../components/AppointmentCard";
import { PatientPicker } from "../components/PatientPicker";
import { apiError, installFakeApi } from "../test/fakeApi";
import { appointment, clockInfo, doctor, patient, renderPage } from "../test/utils";
import Admin from "./Admin";
import Book from "./Book";
import { PatientDetail } from "./Patients";
import Reports from "./Reports";

const base = () => ({
  "GET /clock": { body: clockInfo() },
  "GET /doctors": { body: [doctor()] },
});

describe("check-in, history and corrections", () => {
  it("checks a patient in", async () => {
    const api = installFakeApi({
      ...base(),
      "POST /appointments/41/check-in": {
        body: appointment({ checked_in_at_ist: "2026-11-02T09:45:00+05:30" }),
      },
    });
    const user = userEvent.setup();
    renderPage(
      <AppointmentCard appointment={appointment({ allowed_actions: ["check-in", "cancel"] })} />,
    );
    await user.click(screen.getByRole("button", { name: "Check in" }));
    await waitFor(() => expect(api.count("POST", "/appointments/41/check-in")).toBe(1));
  });

  it("shows the arrival time and the urgent marker", () => {
    installFakeApi(base());
    renderPage(
      <AppointmentCard
        appointment={appointment({
          checked_in_at_ist: "2026-11-02T09:45:00+05:30",
          urgent_symptoms: true,
          allowed_actions: ["complete", "no-show", "cancel"],
        })}
      />,
    );
    expect(screen.getByText("Arrived")).toBeInTheDocument();
    expect(screen.getByText("09:45 IST")).toBeInTheDocument();
    expect(screen.getByText(/Urgent symptoms/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check in" })).not.toBeInTheDocument();
  });

  it("corrects a no-show to completed, with a reason", async () => {
    const api = installFakeApi({
      ...base(),
      "POST /appointments/41/correct": {
        body: appointment({ status: "COMPLETED", allowed_actions: ["correct"] }),
      },
    });
    const user = userEvent.setup();
    renderPage(
      <AppointmentCard
        appointment={appointment({ status: "NO_SHOW", allowed_actions: ["correct"] })}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Correct the outcome…" }));
    const save = screen.getByRole("button", { name: "Save the correction" });
    expect(save).toBeDisabled(); // a reason is required
    await user.type(
      screen.getByLabelText("Why is it being corrected?"),
      "Seen by the cover doctor",
    );
    await user.click(save);
    await waitFor(() => expect(api.count("POST", "/appointments/41/correct")).toBe(1));
    expect(api.last("POST", "/appointments/41/correct")?.body).toEqual({
      status: "COMPLETED",
      note: "Seen by the cover doctor",
    });
  });

  it("offers no correction for a cancelled appointment", () => {
    installFakeApi(base());
    renderPage(
      <AppointmentCard appointment={appointment({ status: "CANCELLED", allowed_actions: [] })} />,
    );
    expect(screen.queryByRole("button", { name: /Correct the outcome/ })).not.toBeInTheDocument();
  });

  it("loads the history only when it is opened", async () => {
    const api = installFakeApi({
      ...base(),
      "GET /appointments/41/history": {
        body: [
          {
            id: 1,
            appointment_id: 41,
            patient_id: 7,
            kind: "BOOKED",
            at_utc: "2026-11-02T02:30:00Z",
            at_ist: "2026-11-02T08:00:00+05:30",
            detail: {},
          },
          {
            id: 2,
            appointment_id: 41,
            patient_id: 7,
            kind: "CORRECTED",
            at_utc: "2026-11-02T06:00:00Z",
            at_ist: "2026-11-02T11:30:00+05:30",
            detail: { from_status: "NO_SHOW", to_status: "COMPLETED", note: "Wrongly marked" },
          },
        ],
      },
    });
    const user = userEvent.setup();
    renderPage(<AppointmentCard appointment={appointment()} />);
    expect(api.count("GET", "/appointments/41/history")).toBe(0);
    await user.click(screen.getByRole("button", { name: "History" }));
    expect(await screen.findByText(/08:00 IST: Booked/)).toBeInTheDocument();
    expect(screen.getByText(/from no-show to completed: Wrongly marked/)).toBeInTheDocument();
  });
});

describe("booking safety", () => {
  const slot = {
    start_at_utc: "2026-11-02T04:30:00Z",
    start_at_ist: "2026-11-02T10:00:00+05:30",
    end_at_utc: "2026-11-02T05:00:00Z",
    end_at_ist: "2026-11-02T10:30:00+05:30",
  };
  const slots = {
    doctor_id: 1,
    date: "2026-11-02",
    slot_length_min: 30,
    source: "WEEKLY",
    windows: [{ start: "09:00", end: "13:00" }],
    slots: [slot],
    unavailable_reason: null,
  };

  it("warns about emergency symptoms while the reason is typed, without blocking", async () => {
    installFakeApi({
      ...base(),
      "GET /patients/7": { body: patient() },
      "GET /doctors/1/slots": { body: slots },
      "POST /triage": {
        body: { urgent: true, message: "Call 112 or go to the nearest emergency department now." },
      },
    });
    const user = userEvent.setup();
    renderPage(<Book />, "/book?patient=7&doctor=1&date=2026-11-02");
    await user.click(await screen.findByRole("button", { name: "10:00–10:30" }));
    await user.type(screen.getByLabelText("Reason"), "chest pain since morning");
    expect(await screen.findByText(/Call 112/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Book the appointment" })).toBeEnabled();
  });

  it("sends the same Idempotency-Key when the same booking is retried", async () => {
    let attempts = 0;
    const api = installFakeApi({
      ...base(),
      "GET /patients/7": { body: patient() },
      "GET /doctors/1/slots": { body: slots },
      "POST /triage": { body: { urgent: false, message: null } },
      "POST /appointments": () => {
        attempts += 1;
        return attempts === 1
          ? apiError(503, "SERVICE_UNAVAILABLE", "busy")
          : { status: 201, body: appointment() };
      },
    });
    const user = userEvent.setup();
    renderPage(<Book />, "/book?patient=7&doctor=1&date=2026-11-02");
    await user.click(await screen.findByRole("button", { name: "10:00–10:30" }));
    await user.type(screen.getByLabelText("Reason"), "Fever");
    const book = screen.getByRole("button", { name: "Book the appointment" });
    await user.click(book);
    await waitFor(() => expect(api.count("POST", "/appointments")).toBe(1));
    await user.click(book);
    await waitFor(() => expect(api.count("POST", "/appointments")).toBe(2));

    const posts = api.calls.filter((c) => c.method === "POST" && c.path === "/appointments");
    const keys = posts.map((c) => c.headers.get("Idempotency-Key"));
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
  });

  it("uses a new key when the booking itself changes", async () => {
    const api = installFakeApi({
      ...base(),
      "GET /patients/7": { body: patient() },
      "GET /doctors/1/slots": { body: slots },
      "POST /triage": { body: { urgent: false, message: null } },
      "POST /appointments": apiError(503, "SERVICE_UNAVAILABLE", "busy"),
    });
    const user = userEvent.setup();
    renderPage(<Book />, "/book?patient=7&doctor=1&date=2026-11-02");
    await user.click(await screen.findByRole("button", { name: "10:00–10:30" }));
    await user.type(screen.getByLabelText("Reason"), "Fever");
    await user.click(screen.getByRole("button", { name: "Book the appointment" }));
    await waitFor(() => expect(api.count("POST", "/appointments")).toBe(1));
    await user.type(screen.getByLabelText("Reason"), " and cough");
    await user.click(screen.getByRole("button", { name: "Book the appointment" }));
    await waitFor(() => expect(api.count("POST", "/appointments")).toBe(2));
    const keys = api.calls
      .filter((c) => c.method === "POST" && c.path === "/appointments")
      .map((c) => c.headers.get("Idempotency-Key"));
    expect(keys[1]).not.toBe(keys[0]);
  });
});

describe("patients", () => {
  it("shows the people who look the same and registers anyway only when told", async () => {
    let attempts: unknown[] = [];
    const api = installFakeApi({
      ...base(),
      "GET /patients": { body: { items: [], total: 0, limit: 10, offset: 0 } },
      "POST /patients": (call) => {
        attempts = [...attempts, call.body];
        return (call.body as { allow_duplicate?: boolean }).allow_duplicate
          ? { status: 201, body: patient({ id: 9, name: "Kavita Nair" }) }
          : apiError(409, "POSSIBLE_DUPLICATE", "same name", {
              candidates: [{ patient_id: 7, name: "Kavita Nair", phone: "+919000000001" }],
            });
      },
    });
    const user = userEvent.setup();
    let chosen: number | null = null;
    renderPage(<PatientPicker onSelect={(p) => (chosen = p.id)} />);
    await user.click(screen.getByRole("button", { name: "New patient" }));
    await user.type(screen.getByLabelText("Name"), "Kavita Nair");
    await user.type(screen.getByLabelText("Phone"), "9876543210");
    await user.type(screen.getByLabelText("Date of birth"), "1990-01-01");
    await user.click(screen.getByRole("button", { name: "Register patient" }));

    expect(await screen.findByText(/same name and date of birth/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use Kavita Nair" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Register anyway" }));
    await waitFor(() => expect(chosen).toBe(9));
    expect(attempts).toHaveLength(2);
    expect(api.last("POST", "/patients")?.body).toMatchObject({ allow_duplicate: true });
  });

  it("changes a phone number from the patient page", async () => {
    const api = installFakeApi({
      ...base(),
      "GET /patients/7": { body: patient() },
      "GET /patients/7/waitlist": { body: [] },
      "GET /patients/7/appointments": { body: { items: [], total: 0, limit: 50, offset: 0 } },
      "PATCH /patients/7": { body: patient({ phone: "+919876543210" }) },
    });
    const user = userEvent.setup();
    renderPage(
      <Routes>
        <Route path="/patients/:id" element={<PatientDetail />} />
      </Routes>,
      "/patients/7",
    );
    const phone = await screen.findByLabelText("Phone", { selector: "input" });
    const save = screen.getByRole("button", { name: "Save changes" });
    expect(save).toBeDisabled(); // nothing changed yet
    await user.clear(phone);
    await user.type(phone, "98765 43210");
    await user.click(save);
    await waitFor(() => expect(api.count("PATCH", "/patients/7")).toBe(1));
    expect(api.last("PATCH", "/patients/7")?.body).toEqual({ phone: "98765 43210" });
  });

  it("offers the full export as a download", async () => {
    installFakeApi({
      ...base(),
      "GET /patients/7": { body: patient() },
      "GET /patients/7/waitlist": { body: [] },
      "GET /patients/7/appointments": { body: { items: [], total: 0, limit: 50, offset: 0 } },
    });
    renderPage(
      <Routes>
        <Route path="/patients/:id" element={<PatientDetail />} />
      </Routes>,
      "/patients/7",
    );
    const link = await screen.findByRole("link", { name: "Download all their records" });
    expect(link.getAttribute("href")).toMatch(/\/patients\/7\/export$/);
  });

  it("keeps a place in the queue when an offer is turned down", async () => {
    const offered: WaitlistEntry = {
      id: 5,
      doctor_id: 1,
      doctor_name: "Dr. Rao",
      patient_id: 7,
      patient_name: "Kavita Nair",
      patient_phone: "+919000000001",
      date: "2026-11-02",
      status: "OFFERED",
      position: null,
      offered_start_at_utc: "2026-11-02T04:30:00Z",
      offered_start_at_ist: "2026-11-02T10:00:00+05:30",
      offer_expires_at_utc: "2026-11-02T05:00:00Z",
      offer_expires_at_ist: "2026-11-02T10:30:00+05:30",
      appointment_id: null,
    };
    const api = installFakeApi({
      ...base(),
      "GET /patients/7": { body: patient() },
      "GET /patients/7/waitlist": { body: [offered] },
      "GET /patients/7/appointments": { body: { items: [], total: 0, limit: 50, offset: 0 } },
      "POST /waitlist/5/decline": { body: { ...offered, status: "WAITING", position: 1 } },
    });
    const user = userEvent.setup();
    renderPage(
      <Routes>
        <Route path="/patients/:id" element={<PatientDetail />} />
      </Routes>,
      "/patients/7",
    );
    await user.click(await screen.findByRole("button", { name: "Not this one (keep my place)" }));
    await waitFor(() => expect(api.count("POST", "/waitlist/5/decline")).toBe(1));
    expect(api.count("DELETE", "/waitlist/5")).toBe(0);
  });
});

describe("doctors and the report", () => {
  it("switches a doctor off for new bookings", async () => {
    const api = installFakeApi({
      ...base(),
      "GET /doctors/1/weekly-windows": { body: { windows: [], needs_attention: [] } },
      "GET /doctors/1/overrides": { body: [] },
      "GET /appointments": { body: { items: [], total: 0, limit: 100, offset: 0 } },
      "PATCH /doctors/1": { body: doctor({ accepting_bookings: false }) },
    });
    const user = userEvent.setup();
    renderPage(<Admin />, "/admin");
    await user.click(await screen.findByLabelText("Taking new bookings"));
    await user.click(screen.getByRole("button", { name: "Save details" }));
    await waitFor(() => expect(api.count("PATCH", "/doctors/1")).toBe(1));
    expect(api.last("PATCH", "/doctors/1")?.body).toMatchObject({ accepting_bookings: false });
  });

  it("shows the report with rates", async () => {
    const row: DoctorReport = {
      doctor_id: 1,
      doctor_name: "Dr. Rao",
      capacity_slots: 8,
      appointments: 6,
      new_bookings: 5,
      booked: 1,
      completed: 1,
      no_show: 1,
      cancelled: 1,
      late_cancelled: 1,
      rescheduled: 1,
      checked_in: 0,
      utilisation: 0.375,
      no_show_rate: 0.5,
    };
    const api = installFakeApi({
      ...base(),
      "GET /reports/summary": {
        body: {
          start: "2026-10-27",
          end: "2026-11-02",
          doctors: [row],
          total: { ...row, doctor_id: 0, doctor_name: "All doctors" },
        },
      },
    });
    renderPage(<Reports />, "/reports");
    expect((await screen.findAllByText("38%")).length).toBe(2); // utilisation 0.375, rounded
    expect(screen.getAllByText("50%").length).toBeGreaterThan(0);
    expect(screen.getByText("All doctors")).toBeInTheDocument();
    expect(api.last("GET", "/reports/summary")?.query).toMatchObject({ to: "2026-11-02" });
  });
});
