// Response shapes of the API (backend/app/api/schemas/responses.py). Every instant comes twice,
// as `..._utc` and `..._ist`; the UI shows the IST one and never converts times itself.

export type Status = "BOOKED" | "COMPLETED" | "CANCELLED" | "LATE_CANCELLED" | "NO_SHOW";
export type Action = "cancel" | "reschedule" | "complete" | "no-show" | "check-in" | "correct";
export type CancelledBy = "PATIENT" | "CLINIC";

export interface Doctor {
  id: number;
  name: string;
  speciality: string;
  slot_length_min: number;
  daily_cap: number;
  accepting_bookings: boolean;
}

export interface TimeWindow {
  start: string; // HH:MM, "24:00" allowed for the end
  end: string;
}

export interface WeeklyWindow extends TimeWindow {
  weekday: number; // Monday is 0
}

export interface Strike {
  appointment_id: number;
  type: "NO_SHOW" | "LATE_CANCELLED";
  at_utc: string;
  at_ist: string;
}

export interface Deposit {
  required: boolean;
  required_until_utc: string | null;
  required_until_ist: string | null;
  reasons: Strike[];
}

export interface Patient {
  id: number;
  name: string;
  phone: string;
  date_of_birth: string;
  created_at_utc: string;
  deposit_required: boolean | null; // null in search results
  deposit: Deposit | null; // null in search results
}

export interface WaitlistEntry {
  id: number;
  doctor_id: number;
  doctor_name: string;
  patient_id: number;
  patient_name: string;
  patient_phone: string;
  date: string;
  status: "WAITING" | "OFFERED" | "BOOKED" | "CANCELLED" | "EXPIRED";
  position: number | null;
  offered_start_at_utc: string | null;
  offered_start_at_ist: string | null;
  offer_expires_at_utc: string | null;
  offer_expires_at_ist: string | null;
  appointment_id: number | null;
}

export interface WaitlistAcceptResponse {
  entry: WaitlistEntry;
  appointment: Appointment;
}

export interface SeriesResponse {
  appointments: Appointment[];
}

export interface Appointment {
  id: number;
  doctor_id: number;
  doctor_name: string;
  patient_id: number;
  patient_name: string;
  patient_phone: string;
  status: Status;
  start_at_utc: string;
  start_at_ist: string;
  end_at_utc: string;
  end_at_ist: string;
  reason: string;
  deposit_required_at_booking: boolean;
  deposit_confirmed: boolean;
  cancelled_at_utc: string | null;
  cancelled_at_ist: string | null;
  cancelled_by: CancelledBy | null;
  status_changed_at_utc: string | null;
  status_changed_at_ist: string | null;
  rescheduled_to_id: number | null;
  needs_attention: boolean;
  allowed_actions: Action[];
  checked_in_at_utc: string | null;
  checked_in_at_ist: string | null;
  urgent_symptoms: boolean;
  slots: number; // how many of the doctor's slots the visit lasts
  duration_min: number;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Slot {
  start_at_utc: string;
  start_at_ist: string;
  end_at_utc: string;
  end_at_ist: string;
}

export type UnavailableReason =
  "NO_AVAILABILITY" | "DAILY_CAP_REACHED" | "FULLY_BOOKED" | "DATE_IN_PAST" | "DATE_TOO_FAR";

export type HoursSource = "WEEKLY" | "OVERRIDE";

export interface SlotsResponse {
  doctor_id: number;
  date: string;
  slot_length_min: number;
  source: HoursSource;
  windows: TimeWindow[];
  slots: Slot[];
  unavailable_reason: UnavailableReason | null;
  duration_min: number; // the visit length each listed start is free for
}

/** A bookable start offered instead of the one asked for (same doctor later, or another doctor). */
export interface Alternative extends Slot {
  doctor_id: number;
  doctor_name: string;
  speciality: string;
  same_doctor: boolean;
}

export type SlotState = "FREE" | "BOOKED" | "PAST" | "CAPPED" | "CLOSED" | "BUSY";

export interface ScheduleSlot extends Slot {
  state: SlotState;
  appointment: Appointment | null;
}

export interface ScheduleResponse {
  doctor_id: number;
  date: string;
  slot_length_min: number;
  source: HoursSource;
  windows: TimeWindow[];
  slots: ScheduleSlot[];
  outside_availability: Appointment[];
  unavailable_reason: UnavailableReason | null;
}

export interface WeeklyResponse {
  windows: WeeklyWindow[];
  needs_attention: Appointment[];
}

export interface OverrideResponse {
  date: string;
  note: string | null;
  windows: TimeWindow[];
  needs_attention: Appointment[];
}

export interface CancelResponse {
  appointment: Appointment;
  late: boolean;
  deposit: Deposit;
}

export interface RescheduleResponse {
  old: Appointment;
  new: Appointment;
}

export interface ClockInfo {
  now_utc: string;
  now_ist: string;
  source: "REAL" | "HEADER";
  test_clock_enabled: boolean;
  seed_anchor_date: string | null;
  seed_queue_day: string | null;
}

// What the API returns for any failure.
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
    request_id: string;
  };
}

export interface AppointmentEvent {
  id: number;
  appointment_id: number;
  patient_id: number;
  kind: string;
  at_utc: string;
  at_ist: string;
  detail: Record<string, unknown>;
  actor: string;
}

export interface Triage {
  urgent: boolean;
  message: string | null;
}

export interface DoctorReport {
  doctor_id: number;
  doctor_name: string;
  capacity_slots: number;
  appointments: number;
  new_bookings: number;
  booked: number;
  completed: number;
  no_show: number;
  cancelled: number;
  late_cancelled: number;
  rescheduled: number;
  checked_in: number;
  utilisation: number | null;
  no_show_rate: number | null;
  freed_slots: number;
  refilled: number;
  refilled_via_waitlist: number;
  recovery_rate: number | null;
}

export interface Report {
  start: string;
  end: string;
  doctors: DoctorReport[];
  total: DoctorReport;
}

export interface ProofCase {
  id: string;
  rule: string;
  scenario: string;
  expected: string;
  observed: string;
  passed: boolean;
}

/** The rule scenarios run on the server inside a transaction that is rolled back. */
export interface ProofReport {
  passed: boolean;
  rows_before: number;
  rows_after: number;
  cases: ProofCase[];
}
