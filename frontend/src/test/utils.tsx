import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { ClockProvider } from "../lib/clock";
import type { Appointment, ClockInfo, Deposit, Doctor, Patient } from "../api/types";

/** Renders a page the way main.tsx does, with a fresh query cache per test. */
export function renderPage(ui: ReactElement, route = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <ClockProvider>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </ClockProvider>
    </QueryClientProvider>,
  );
  return { client, ...view };
}

export const doctor = (overrides: Partial<Doctor> = {}): Doctor => ({
  id: 1,
  name: "Dr. Rao",
  speciality: "General",
  slot_length_min: 30,
  daily_cap: 6,
  accepting_bookings: true,
  ...overrides,
});

export const noDeposit: Deposit = {
  required: false,
  required_until_utc: null,
  required_until_ist: null,
  reasons: [],
};

export const flaggedDeposit: Deposit = {
  required: true,
  required_until_utc: "2026-11-27T09:40:00Z",
  required_until_ist: "2026-11-27T15:10:00+05:30",
  reasons: [
    {
      appointment_id: 12,
      type: "NO_SHOW",
      at_utc: "2026-10-29T04:30:00Z",
      at_ist: "2026-10-29T10:00:00+05:30",
    },
    {
      appointment_id: 9,
      type: "LATE_CANCELLED",
      at_utc: "2026-10-28T09:40:00Z",
      at_ist: "2026-10-28T15:10:00+05:30",
    },
  ],
};

export const patient = (overrides: Partial<Patient> = {}): Patient => ({
  id: 7,
  name: "Kavita Nair",
  phone: "+919000000001",
  date_of_birth: "1990-01-01",
  created_at_utc: "2026-10-01T00:00:00Z",
  deposit_required: false,
  deposit: noDeposit,
  ...overrides,
});

export const appointment = (overrides: Partial<Appointment> = {}): Appointment => ({
  id: 41,
  doctor_id: 1,
  doctor_name: "Dr. Rao",
  patient_id: 7,
  patient_name: "Kavita Nair",
  patient_phone: "+919000000001",
  status: "BOOKED",
  start_at_utc: "2026-11-02T04:30:00Z",
  start_at_ist: "2026-11-02T10:00:00+05:30",
  end_at_utc: "2026-11-02T05:00:00Z",
  end_at_ist: "2026-11-02T10:30:00+05:30",
  reason: "Fever, 3 days",
  deposit_required_at_booking: false,
  deposit_confirmed: false,
  cancelled_at_utc: null,
  cancelled_at_ist: null,
  cancelled_by: null,
  status_changed_at_utc: null,
  status_changed_at_ist: null,
  rescheduled_to_id: null,
  needs_attention: false,
  allowed_actions: ["cancel", "reschedule"],
  checked_in_at_utc: null,
  checked_in_at_ist: null,
  urgent_symptoms: false,
  slots: 1,
  duration_min: 30,
  ...overrides,
});

export const clockInfo = (overrides: Partial<ClockInfo> = {}): ClockInfo => ({
  now_utc: "2026-11-02T02:30:00Z",
  now_ist: "2026-11-02T08:00:00+05:30",
  source: "REAL",
  test_clock_enabled: true,
  seed_anchor_date: "2026-10-17",
  seed_queue_day: "2026-10-19",
  ...overrides,
});
