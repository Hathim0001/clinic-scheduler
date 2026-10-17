import { request } from "./client";
import type {
  Appointment,
  CancelledBy,
  CancelResponse,
  ClockInfo,
  Doctor,
  OverrideResponse,
  Page,
  Patient,
  RescheduleResponse,
  ScheduleResponse,
  SlotsResponse,
  Status,
  TimeWindow,
  WeeklyResponse,
  WeeklyWindow,
} from "./types";

export interface BookBody {
  doctor_id: number;
  patient_id: number;
  start_at: string;
  reason: string;
  deposit_confirmed?: boolean;
}

export interface RescheduleBody {
  start_at: string;
  doctor_id?: number;
  deposit_confirmed?: boolean;
}

export interface NewPatient {
  name: string;
  phone: string;
  date_of_birth: string;
}

export interface DoctorChanges {
  name?: string;
  speciality?: string;
  daily_cap?: number;
  slot_length_min?: number;
}

// One function per endpoint. The components never build URLs or read response headers.
export const api = {
  clock: () => request<ClockInfo>("GET", "/clock"),

  doctors: () => request<Doctor[]>("GET", "/doctors"),
  updateDoctor: (id: number, changes: DoctorChanges) =>
    request<Doctor>("PATCH", `/doctors/${id}`, { body: changes }),

  weeklyWindows: (doctorId: number) =>
    request<WeeklyResponse>("GET", `/doctors/${doctorId}/weekly-windows`),
  saveWeeklyWindows: (doctorId: number, windows: WeeklyWindow[], acknowledge: boolean) =>
    request<WeeklyResponse>("PUT", `/doctors/${doctorId}/weekly-windows`, {
      body: { windows, acknowledge_conflicts: acknowledge },
    }),
  overrides: (doctorId: number, from: string, to: string) =>
    request<OverrideResponse[]>("GET", `/doctors/${doctorId}/overrides`, { query: { from, to } }),
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

  slots: (doctorId: number, date: string, patientId?: number) =>
    request<SlotsResponse>("GET", `/doctors/${doctorId}/slots`, {
      query: { date, patient_id: patientId },
    }),
  schedule: (doctorId: number, date: string) =>
    request<ScheduleResponse>("GET", `/doctors/${doctorId}/schedule`, { query: { date } }),

  searchPatients: (query: { phone?: string; q?: string; limit?: number; offset?: number }) =>
    request<Page<Patient>>("GET", "/patients", { query }),
  patient: (id: number) => request<Patient>("GET", `/patients/${id}`),
  createPatient: (body: NewPatient) => request<Patient>("POST", "/patients", { body }),
  patientAppointments: (id: number, limit = 50) =>
    request<Page<Appointment>>("GET", `/patients/${id}/appointments`, { query: { limit } }),

  appointment: (id: number) => request<Appointment>("GET", `/appointments/${id}`),
  appointments: (query: {
    doctor_id?: number;
    date?: string;
    status?: Status;
    needs_attention?: boolean;
    limit?: number;
    offset?: number;
  }) => request<Page<Appointment>>("GET", "/appointments", { query }),
  book: (body: BookBody) => request<Appointment>("POST", "/appointments", { body }),
  cancel: (id: number, cancelledBy: CancelledBy) =>
    request<CancelResponse>("POST", `/appointments/${id}/cancel`, {
      body: { cancelled_by: cancelledBy },
    }),
  reschedule: (id: number, body: RescheduleBody) =>
    request<RescheduleResponse>("POST", `/appointments/${id}/reschedule`, { body }),
  complete: (id: number) => request<Appointment>("POST", `/appointments/${id}/complete`),
  noShow: (id: number) => request<Appointment>("POST", `/appointments/${id}/no-show`),

  queue: (query: { date?: string; doctor_id?: number; include_cancelled?: boolean }) =>
    request<Appointment[]>("GET", "/queue", { query }),
};
