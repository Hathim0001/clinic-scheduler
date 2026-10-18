import { request } from "./client";
import type {
  ProofReport,
  Alternative,
  Appointment,
  AppointmentEvent,
  CancelledBy,
  CancelResponse,
  ClockInfo,
  Doctor,
  SeriesResponse,
  WaitlistAcceptResponse,
  WaitlistEntry,
  OverrideResponse,
  Page,
  Patient,
  Report,
  RescheduleResponse,
  ScheduleResponse,
  SlotsResponse,
  Status,
  TimeWindow,
  Triage,
  WeeklyResponse,
  WeeklyWindow,
} from "./types";

export interface BookBody {
  doctor_id: number;
  patient_id: number;
  start_at: string;
  reason: string;
  deposit_confirmed?: boolean;
  slots?: number; // the visit's length in the doctor's slots (1 to 4)
  /** Sent as the Idempotency-Key header, so a retry cannot book twice. */
  idempotencyKey?: string;
}

export interface NewDoctor {
  name: string;
  speciality: string;
  slot_length_min: number;
  daily_cap: number;
}

export interface SeriesBody extends BookBody {
  every_days: number;
  count: number;
}

export interface RescheduleBody {
  start_at: string;
  doctor_id?: number;
  deposit_confirmed?: boolean;
  by?: CancelledBy; // who is moving it; a clinic move is never a late cancellation
  acknowledge_late?: boolean; // accept that a patient move inside 2 hours counts as a late cancel
}

export interface NewPatient {
  name: string;
  phone: string;
  date_of_birth: string;
  allow_duplicate?: boolean;
}

export interface PatientChanges {
  name?: string;
  phone?: string;
  date_of_birth?: string;
  allow_duplicate?: boolean;
}

export interface DoctorChanges {
  name?: string;
  speciality?: string;
  daily_cap?: number;
  slot_length_min?: number;
  accepting_bookings?: boolean;
}

export interface LoginResult {
  token: string;
  name: string;
  expires_at_epoch: number;
}

// One function per endpoint. The components never build URLs or read response headers.
export const api = {
  clock: () => request<ClockInfo>("GET", "/clock"),
  authStatus: () => request<{ required: boolean }>("GET", "/auth/status"),
  login: (name: string, password: string) =>
    request<LoginResult>("POST", "/auth/login", { body: { name, password } }),

  doctors: () => request<Doctor[]>("GET", "/doctors"),
  createDoctor: (body: NewDoctor) => request<Doctor>("POST", "/doctors", { body }),
  deleteDoctor: (id: number) => request<void>("DELETE", `/doctors/${id}`),
  updateDoctor: (id: number, changes: DoctorChanges) =>
    request<Doctor>("PATCH", `/doctors/${id}`, { body: changes }),

  weeklyWindows: (doctorId: number) =>
    request<WeeklyResponse>("GET", `/doctors/${doctorId}/weekly-windows`),
  saveWeeklyWindows: (doctorId: number, windows: WeeklyWindow[], acknowledge: boolean) =>
    request<WeeklyResponse>("PUT", `/doctors/${doctorId}/weekly-windows`, {
      body: { windows, acknowledge_conflicts: acknowledge },
    }),
  overrides: (doctorId: number, from: string, to: string) =>
    request<OverrideResponse[]>("GET", `/doctors/${doctorId}/overrides`, {
      query: { from, to },
    }),
  saveOverride: (
    doctorId: number,
    date: string,
    windows: TimeWindow[],
    note: string,
    acknowledge: boolean,
  ) =>
    request<OverrideResponse>("PUT", `/doctors/${doctorId}/overrides/${date}`, {
      body: { windows, note: note || null, acknowledge_conflicts: acknowledge },
    }),
  deleteOverride: (doctorId: number, date: string, acknowledge: boolean) =>
    request<void>("DELETE", `/doctors/${doctorId}/overrides/${date}`, {
      query: { acknowledge_conflicts: acknowledge },
    }),

  alternatives: (doctorId: number, date: string, patientId?: number, slots = 1) =>
    request<Alternative[]>("GET", "/alternatives", {
      query: { doctor_id: doctorId, date, patient_id: patientId, slots },
    }),
  slots: (doctorId: number, date: string, patientId?: number, slots = 1) =>
    request<SlotsResponse>("GET", `/doctors/${doctorId}/slots`, {
      query: { date, patient_id: patientId, slots },
    }),
  schedule: (doctorId: number, date: string) =>
    request<ScheduleResponse>("GET", `/doctors/${doctorId}/schedule`, {
      query: { date },
    }),

  searchPatients: (query: { phone?: string; q?: string; limit?: number; offset?: number }) =>
    request<Page<Patient>>("GET", "/patients", { query }),
  patient: (id: number) => request<Patient>("GET", `/patients/${id}`),
  createPatient: (body: NewPatient) => request<Patient>("POST", "/patients", { body }),
  updatePatient: (id: number, changes: PatientChanges) =>
    request<Patient>("PATCH", `/patients/${id}`, { body: changes }),
  patientAppointments: (id: number, limit = 50) =>
    request<Page<Appointment>>("GET", `/patients/${id}/appointments`, {
      query: { limit },
    }),

  appointment: (id: number) => request<Appointment>("GET", `/appointments/${id}`),
  appointments: (query: {
    doctor_id?: number;
    date?: string;
    status?: Status;
    needs_attention?: boolean;
    limit?: number;
    offset?: number;
  }) => request<Page<Appointment>>("GET", "/appointments", { query }),
  book: ({ idempotencyKey, ...body }: BookBody) =>
    request<Appointment>("POST", "/appointments", {
      body,
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    }),
  checkIn: (id: number) => request<Appointment>("POST", `/appointments/${id}/check-in`),
  correct: (id: number, status: Status, note: string) =>
    request<Appointment>("POST", `/appointments/${id}/correct`, { body: { status, note } }),
  history: (id: number) => request<AppointmentEvent[]>("GET", `/appointments/${id}/history`),
  bookSeries: (body: SeriesBody) =>
    request<SeriesResponse>("POST", "/appointments/recurring", { body }),
  cancel: (id: number, cancelledBy: CancelledBy) =>
    request<CancelResponse>("POST", `/appointments/${id}/cancel`, {
      body: { cancelled_by: cancelledBy },
    }),
  reschedule: (id: number, body: RescheduleBody) =>
    request<RescheduleResponse>("POST", `/appointments/${id}/reschedule`, {
      body,
    }),
  complete: (id: number) => request<Appointment>("POST", `/appointments/${id}/complete`),
  noShow: (id: number) => request<Appointment>("POST", `/appointments/${id}/no-show`),

  joinWaitlist: (doctorId: number, patientId: number, date: string) =>
    request<WaitlistEntry>("POST", `/doctors/${doctorId}/waitlist`, {
      body: { patient_id: patientId, date },
    }),
  doctorWaitlist: (doctorId: number, date: string) =>
    request<WaitlistEntry[]>("GET", `/doctors/${doctorId}/waitlist`, {
      query: { date },
    }),
  patientWaitlist: (patientId: number) =>
    request<WaitlistEntry[]>("GET", `/patients/${patientId}/waitlist`),
  declineOffer: (id: number) => request<WaitlistEntry>("POST", `/waitlist/${id}/decline`),
  leaveWaitlist: (id: number) => request<WaitlistEntry>("DELETE", `/waitlist/${id}`),
  acceptOffer: (id: number, reason: string, depositConfirmed: boolean) =>
    request<WaitlistAcceptResponse>("POST", `/waitlist/${id}/accept`, {
      body: { reason, deposit_confirmed: depositConfirmed },
    }),

  report: (from: string, to: string) =>
    request<Report>("GET", "/reports/summary", { query: { from, to } }),
  runProof: () => request<ProofReport>("POST", "/proof"),
  triage: (text: string) => request<Triage>("POST", "/triage", { body: { text } }),

  queue: (query: { date?: string; doctor_id?: number; include_cancelled?: boolean }) =>
    request<Appointment[]>("GET", "/queue", { query }),
};
