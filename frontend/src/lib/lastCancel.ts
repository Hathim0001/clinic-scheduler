import { useSyncExternalStore } from "react";
import type { Appointment } from "../api/types";

/**
 * The cancellation made most recently, kept outside the page that made it: the queue drops a
 * cancelled row at once, and the undo has to outlive the row for the few minutes it is offered.
 */
export interface LastCancel {
  appointment: Appointment;
  at: number;
}

let current: LastCancel | null = null;
const listeners = new Set<() => void>();

const emit = () => listeners.forEach((listener) => listener());

export function rememberCancel(appointment: Appointment): void {
  // Only a cancellation the server says can still be undone is worth showing.
  current = appointment.allowed_actions.includes("undo-cancel")
    ? { appointment, at: Date.now() }
    : null;
  emit();
}

export function forgetCancel(): void {
  current = null;
  emit();
}

export function useLastCancel(): LastCancel | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
  );
}
