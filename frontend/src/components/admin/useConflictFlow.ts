import { useState } from "react";
import { ApiError } from "../../api/client";
import { conflictedAppointments, type ConflictedAppointment } from "../ConflictDialog";

interface Conflict {
  message: string;
  appointments: ConflictedAppointment[];
}

/**
 * A change to the hours that would leave booked appointments outside them is refused by the server
 * with the list. This turns that one error into a dialog; "Save anyway" sends the change again with
 * the acknowledgement. Every other error is shown as a normal banner.
 */
export function useConflictFlow() {
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const intercept = (error: unknown) => {
    if (error instanceof ApiError && error.code === "AVAILABILITY_CONFLICTS") {
      setConflict({
        message: error.message,
        appointments: conflictedAppointments(error.details),
      });
    }
  };
  return { conflict, intercept, clear: () => setConflict(null) };
}
