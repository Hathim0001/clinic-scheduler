import { ApiError } from "../api/client";

export interface FriendlyError {
  /** The sentence to show. Never raw JSON. */
  message: string;
  /** Extra lines, for example the invalid fields of a form. */
  lines: string[];
  code: string;
  /** Quote this when reporting a problem: it finds the request in the server logs. */
  requestId: string | null;
  /** Whether a "Try again" button makes sense (the server was busy or unreachable). */
  retryable: boolean;
}

interface Context {
  doctorName?: string;
}

function fieldLines(details: Record<string, unknown>): string[] {
  const fields = details.fields;
  if (!Array.isArray(fields)) return [];
  return fields.slice(0, 8).map((field) => {
    const { loc, msg } = field as { loc?: unknown[]; msg?: string };
    const where = (loc ?? []).filter((part) => part !== "body" && part !== "query").join(".");
    return where ? `${where}: ${msg ?? "invalid"}` : String(msg ?? "invalid");
  });
}

// What the receptionist reads for each error code (plan section 25.1).
export function describeError(error: unknown, context: Context = {}): FriendlyError {
  if (!(error instanceof ApiError)) {
    return {
      message: "Something unexpected went wrong in the page.",
      lines: [],
      code: "UI_ERROR",
      requestId: null,
      retryable: false,
    };
  }
  const doctor = context.doctorName ?? "The doctor";
  const base = { lines: [], code: error.code, requestId: error.requestId, retryable: false };
  switch (error.code) {
    case "SLOT_TAKEN":
      return {
        ...base,
        message:
          error.details.same_patient === true
            ? "This patient is already booked in this slot."
            : "Someone just booked this slot. The list has been refreshed.",
      };
    case "PATIENT_OVERLAP":
      return { ...base, message: "This patient already has an appointment at that time." };
    case "DAILY_CAP_REACHED":
      return { ...base, message: `${doctor} is fully booked on that day.` };
    case "OUTSIDE_AVAILABILITY":
    case "OFF_GRID":
      return {
        ...base,
        message: `${doctor} is not available at that time. Pick one of the listed slots.`,
      };
    case "BOOKING_IN_PAST":
      return { ...base, message: "That time has passed." };
    case "BOOKING_TOO_FAR":
      return { ...base, message: "Bookings open up to 60 days ahead." };
    case "DEPOSIT_REQUIRED":
      return {
        ...base,
        message:
          "This patient has missed or cancelled late twice recently. Tick the deposit box to book.",
      };
    case "APPOINTMENT_ALREADY_STARTED":
      return {
        ...base,
        message: "This appointment has already started, so it can no longer be cancelled or moved.",
      };
    case "TOO_EARLY_TO_MARK":
      return {
        ...base,
        message: error.message.startsWith("Check-in")
          ? error.message
          : "An appointment can only be marked once it has started.",
      };
    case "RESCHEDULE_NO_CHANGE":
      return { ...base, message: "Pick a different time or doctor to move this appointment." };
    case "PHONE_TAKEN":
      return {
        ...base,
        message:
          "A patient with this phone number is already registered. Search by phone to find them.",
      };
    case "FORBIDDEN":
      return { ...base, message: "Only an administrator can do this." };
    case "LAST_ADMIN":
      return {
        ...base,
        message:
          "This is the last active administrator. Make someone else an administrator first, so the clinic cannot lock itself out.",
      };
    case "STAFF_USERNAME_TAKEN":
      return { ...base, message: "That username is already in use. Pick another." };
    case "PATIENT_HAS_UPCOMING":
      return {
        ...base,
        message:
          "This patient still has an upcoming appointment or a waitlist place. Cancel or complete those first, then erase.",
      };
    case "PATIENT_ERASED":
      return {
        ...base,
        message:
          "This patient's data was erased, so they cannot be booked or edited. Register them again if they return.",
      };
    case "LATE_RESCHEDULE_NEEDS_CONFIRMATION":
      return { ...base, message: error.message };
    case "DOCTOR_NOT_ACCEPTING":
      return { ...base, message: `${doctor} is not taking new bookings at the moment.` };
    case "ALREADY_CHECKED_IN":
      return {
        ...base,
        message: "The patient has already checked in. Only the clinic can cancel from here.",
      };
    case "INVALID_CORRECTION":
      return { ...base, message: "That outcome cannot be changed to the one chosen." };
    case "IDEMPOTENCY_KEY_REUSED":
      return {
        ...base,
        message: "This request was already sent with different details. Reload and try again.",
      };
    case "SERVICE_UNAVAILABLE":
      return {
        ...base,
        message: "The server is busy or waking up. Try again in a few seconds.",
        retryable: true,
      };
    case "NETWORK_ERROR":
      return {
        ...base,
        message: "Cannot reach the server. Check the connection and try again.",
        retryable: true,
      };
    case "VALIDATION_ERROR":
      return {
        ...base,
        message: "Some fields are missing or invalid.",
        lines: fieldLines(error.details),
      };
    default:
      // INVALID_TRANSITION already names the status; everything else shows the words of the server.
      return { ...base, message: error.message };
  }
}

export const REASON_TEXT: Record<string, string> = {
  NO_AVAILABILITY: "The doctor is not working on this date.",
  DAILY_CAP_REACHED: "The doctor has reached the daily limit of appointments for this date.",
  FULLY_BOOKED: "Every slot on this date is taken.",
  DATE_IN_PAST: "This date, or the rest of it, has passed.",
  DATE_TOO_FAR: "Bookings open up to 60 days ahead.",
  NOT_ACCEPTING: "The doctor is not taking new bookings at the moment.",
};

const SPOKEN_STATUS: Record<string, string> = {
  COMPLETED: "already completed",
  CANCELLED: "cancelled",
  LATE_CANCELLED: "cancelled late",
  NO_SHOW: "marked as a no-show",
};

// Why a button is switched off. The server decided (`allowed_actions`); this only words it.
export function whyDisabled(action: string, status: string): string {
  if (status !== "BOOKED") {
    return `This appointment is ${SPOKEN_STATUS[status] ?? status.toLowerCase()}, so it cannot be changed.`;
  }
  return action === "complete" || action === "no-show"
    ? "Cannot mark this appointment before it starts."
    : "This appointment has already started, so it can no longer be cancelled or moved.";
}
