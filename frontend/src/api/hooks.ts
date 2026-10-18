import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./endpoints";
import type {
  BookBody,
  DoctorChanges,
  NewDoctor,
  NewPatient,
  PatientChanges,
  RescheduleBody,
  SeriesBody,
} from "./endpoints";
import type { CancelledBy, Status, TimeWindow, WeeklyWindow } from "./types";

// Query hooks. The keys start with the resource name so a mutation can refresh what shows it.

export const useClockInfo = () =>
  useQuery({
    queryKey: ["clock"],
    queryFn: api.clock,
    refetchInterval: 30_000,
  });

/** Does this server ask for a staff sign-in? It rarely changes, so it is asked once. */
export const useAuthStatus = () =>
  useQuery({ queryKey: ["authStatus"], queryFn: api.authStatus, staleTime: Infinity, retry: 1 });

export const useDoctors = () => useQuery({ queryKey: ["doctors"], queryFn: api.doctors });

export const useSlots = (doctorId: number | null, date: string, patientId?: number, slots = 1) =>
  useQuery({
    queryKey: ["slots", doctorId, date, patientId ?? null, slots],
    queryFn: () => api.slots(doctorId as number, date, patientId, slots),
    enabled: doctorId !== null && date !== "",
  });

export const useSchedule = (doctorId: number | null, date: string) =>
  useQuery({
    queryKey: ["schedule", doctorId, date],
    queryFn: () => api.schedule(doctorId as number, date),
    enabled: doctorId !== null && date !== "",
  });

export const usePatientSearch = (query: { phone?: string; q?: string }, limit = 10) =>
  useQuery({
    queryKey: ["patients", query, limit],
    queryFn: () => api.searchPatients({ ...query, limit }),
    placeholderData: (previous) => previous, // keep the list on screen while more is loading
    enabled: Boolean(query.phone || query.q),
  });

export const usePatient = (id: number | null) =>
  useQuery({
    queryKey: ["patient", id],
    queryFn: () => api.patient(id as number),
    enabled: id !== null,
  });

export const usePatientAppointments = (id: number | null, limit = 50) =>
  useQuery({
    queryKey: ["patientAppointments", id, limit],
    queryFn: () => api.patientAppointments(id as number, limit),
    placeholderData: (previous) => previous, // keep the list on screen while more is loading
    enabled: id !== null,
  });

export const useAppointment = (id: number | null) =>
  useQuery({
    queryKey: ["appointment", id],
    queryFn: () => api.appointment(id as number),
    enabled: id !== null,
  });

export const useQueue = (date: string, doctorId: number | null, includeCancelled: boolean) =>
  useQuery({
    queryKey: ["queue", date, doctorId, includeCancelled],
    queryFn: () =>
      api.queue({
        date: date || undefined,
        doctor_id: doctorId ?? undefined,
        include_cancelled: includeCancelled,
      }),
    refetchInterval: 60_000, // the queue is a live screen
  });

export const useNeedsAttention = () =>
  useQuery({
    queryKey: ["needsAttention"],
    queryFn: () => api.appointments({ needs_attention: true, status: "BOOKED", limit: 100 }),
    refetchInterval: 60_000,
  });

export const useWeeklyWindows = (doctorId: number | null) =>
  useQuery({
    queryKey: ["weekly", doctorId],
    queryFn: () => api.weeklyWindows(doctorId as number),
    enabled: doctorId !== null,
  });

export const useOverrides = (doctorId: number | null, from: string, to: string) =>
  useQuery({
    queryKey: ["overrides", doctorId, from, to],
    queryFn: () => api.overrides(doctorId as number, from, to),
    enabled: doctorId !== null && from !== "" && to !== "",
  });

export const useDoctorWaitlist = (doctorId: number | null, date: string) =>
  useQuery({
    queryKey: ["waitlist", "doctor", doctorId, date],
    queryFn: () => api.doctorWaitlist(doctorId as number, date),
    enabled: doctorId !== null && date !== "",
    refetchInterval: 60_000,
  });

export const usePatientWaitlist = (patientId: number | null) =>
  useQuery({
    queryKey: ["waitlist", "patient", patientId],
    queryFn: () => api.patientWaitlist(patientId as number),
    enabled: patientId !== null,
    refetchInterval: 30_000, // offers expire, so keep the countdown honest
  });

export const useAppointmentHistory = (id: number | null, enabled: boolean) =>
  useQuery({
    queryKey: ["appointmentHistory", id],
    queryFn: () => api.history(id as number),
    enabled: enabled && id !== null,
  });

export const useReport = (from: string, to: string) =>
  useQuery({
    queryKey: ["report", from, to],
    queryFn: () => api.report(from, to),
    enabled: from !== "" && to !== "",
  });

/** Does the reason describe symptoms that may need emergency care? A hint, never a block. */
export const useTriage = (text: string) =>
  useQuery({
    queryKey: ["triage", text],
    queryFn: () => api.triage(text),
    enabled: text.trim().length >= 4,
    staleTime: Infinity,
    retry: false,
  });

// Mutations. Each one refreshes only the queries it can change, listed below by the first part of
// their key, instead of everything on screen. The server still decides what is now offered, so the
// lists are refetched rather than patched in place. Changing the test clock is the one change that
// affects every query, and it refreshes them all (see lib/clock.tsx).
const AFFECTS = {
  // a booking, a cancellation, a move, an outcome, a check-in or an accepted offer
  appointments: [
    "slots",
    "schedule",
    "queue",
    "patientAppointments",
    "appointment",
    "appointmentHistory",
    "needsAttention",
    "waitlist",
    "patient", // the deposit flag
    "report",
  ],
  // weekly hours and days off: what is free, and which bookings no longer fit
  hours: [
    "slots",
    "schedule",
    "queue",
    "needsAttention",
    "weekly",
    "overrides",
    "doctors",
    "appointment",
    "patientAppointments",
    "report",
  ],
  // a doctor's own details
  doctors: ["doctors", "slots", "schedule", "weekly", "overrides", "needsAttention"],
  // a patient's name, phone or birth date shows on appointments and queues too
  patients: [
    "patients",
    "patient",
    "patientAppointments",
    "queue",
    "schedule",
    "appointment",
    "waitlist",
  ],
  // joining or leaving the waitlist touches nothing else
  waitlist: ["waitlist"],
} as const;

type Change = keyof typeof AFFECTS;

function useRefreshingMutation<TArgs, TResult>(
  change: Change,
  run: (args: TArgs) => Promise<TResult>,
) {
  const queryClient = useQueryClient();
  const affected: readonly string[] = AFFECTS[change];
  return useMutation({
    mutationFn: run,
    onSettled: () =>
      queryClient.invalidateQueries({
        predicate: (query) => affected.includes(String(query.queryKey[0])),
      }),
  });
}

export const useBook = () =>
  useRefreshingMutation("appointments", (body: BookBody) => api.book(body));

export const useCancel = () =>
  useRefreshingMutation("appointments", (args: { id: number; by: CancelledBy }) =>
    api.cancel(args.id, args.by),
  );

export const useReschedule = () =>
  useRefreshingMutation("appointments", (args: { id: number; body: RescheduleBody }) =>
    api.reschedule(args.id, args.body),
  );

export const useComplete = () =>
  useRefreshingMutation("appointments", (id: number) => api.complete(id));
export const useNoShow = () =>
  useRefreshingMutation("appointments", (id: number) => api.noShow(id));

export const useCreatePatient = () =>
  useRefreshingMutation("patients", (body: NewPatient) => api.createPatient(body));

export const useUpdateDoctor = () =>
  useRefreshingMutation("doctors", (args: { id: number; changes: DoctorChanges }) =>
    api.updateDoctor(args.id, args.changes),
  );

export const useSaveWeekly = () =>
  useRefreshingMutation(
    "hours",
    (args: { doctorId: number; windows: WeeklyWindow[]; acknowledge: boolean }) =>
      api.saveWeeklyWindows(args.doctorId, args.windows, args.acknowledge),
  );

export const useSaveOverride = () =>
  useRefreshingMutation(
    "hours",
    (args: {
      doctorId: number;
      date: string;
      windows: TimeWindow[];
      note: string;
      acknowledge: boolean;
    }) => api.saveOverride(args.doctorId, args.date, args.windows, args.note, args.acknowledge),
  );

export const useDeleteOverride = () =>
  useRefreshingMutation("hours", (args: { doctorId: number; date: string; acknowledge: boolean }) =>
    api.deleteOverride(args.doctorId, args.date, args.acknowledge),
  );

export const useBookSeries = () =>
  useRefreshingMutation("appointments", (body: SeriesBody) => api.bookSeries(body));

export const useCreateDoctor = () =>
  useRefreshingMutation("doctors", (body: NewDoctor) => api.createDoctor(body));

export const useDeleteDoctor = () =>
  useRefreshingMutation("doctors", (id: number) => api.deleteDoctor(id));

export const useJoinWaitlist = () =>
  useRefreshingMutation("waitlist", (args: { doctorId: number; patientId: number; date: string }) =>
    api.joinWaitlist(args.doctorId, args.patientId, args.date),
  );

export const useLeaveWaitlist = () =>
  useRefreshingMutation("waitlist", (id: number) => api.leaveWaitlist(id));

export const useAcceptOffer = () =>
  useRefreshingMutation(
    "appointments",
    (args: { id: number; reason: string; depositConfirmed: boolean }) =>
      api.acceptOffer(args.id, args.reason, args.depositConfirmed),
  );

export const useCheckIn = () =>
  useRefreshingMutation("appointments", (id: number) => api.checkIn(id));

export const useCorrect = () =>
  useRefreshingMutation("appointments", (args: { id: number; status: Status; note: string }) =>
    api.correct(args.id, args.status, args.note),
  );

export const useUpdatePatient = () =>
  useRefreshingMutation("patients", (args: { id: number; changes: PatientChanges }) =>
    api.updatePatient(args.id, args.changes),
  );

export const useDeclineOffer = () =>
  useRefreshingMutation("waitlist", (id: number) => api.declineOffer(id));

export const useLogin = () =>
  useMutation({
    mutationFn: (args: { name: string; password: string }) => api.login(args.name, args.password),
  });
