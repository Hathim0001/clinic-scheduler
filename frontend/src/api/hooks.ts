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

export const useDoctors = () => useQuery({ queryKey: ["doctors"], queryFn: api.doctors });

export const useSlots = (doctorId: number | null, date: string, patientId?: number) =>
  useQuery({
    queryKey: ["slots", doctorId, date, patientId ?? null],
    queryFn: () => api.slots(doctorId as number, date, patientId),
    enabled: doctorId !== null && date !== "",
  });

export const useSchedule = (doctorId: number | null, date: string) =>
  useQuery({
    queryKey: ["schedule", doctorId, date],
    queryFn: () => api.schedule(doctorId as number, date),
    enabled: doctorId !== null && date !== "",
  });

export const usePatientSearch = (query: { phone?: string; q?: string }) =>
  useQuery({
    queryKey: ["patients", query],
    queryFn: () => api.searchPatients({ ...query, limit: 10 }),
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

// Mutations. Anything that changes a booking or the hours can change every list on screen, and the
// server decides what is now offered, so the simple and safe choice is to refresh all queries.
function useRefreshingMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSettled: () => queryClient.invalidateQueries(),
  });
}

export const useBook = () => useRefreshingMutation((body: BookBody) => api.book(body));

export const useCancel = () =>
  useRefreshingMutation((args: { id: number; by: CancelledBy }) => api.cancel(args.id, args.by));

export const useReschedule = () =>
  useRefreshingMutation((args: { id: number; body: RescheduleBody }) =>
    api.reschedule(args.id, args.body),
  );

export const useComplete = () => useRefreshingMutation((id: number) => api.complete(id));
export const useNoShow = () => useRefreshingMutation((id: number) => api.noShow(id));

export const useCreatePatient = () =>
  useRefreshingMutation((body: NewPatient) => api.createPatient(body));

export const useUpdateDoctor = () =>
  useRefreshingMutation((args: { id: number; changes: DoctorChanges }) =>
    api.updateDoctor(args.id, args.changes),
  );

export const useSaveWeekly = () =>
  useRefreshingMutation(
    (args: { doctorId: number; windows: WeeklyWindow[]; acknowledge: boolean }) =>
      api.saveWeeklyWindows(args.doctorId, args.windows, args.acknowledge),
  );

export const useSaveOverride = () =>
  useRefreshingMutation(
    (args: {
      doctorId: number;
      date: string;
      windows: TimeWindow[];
      note: string;
      acknowledge: boolean;
    }) => api.saveOverride(args.doctorId, args.date, args.windows, args.note, args.acknowledge),
  );

export const useDeleteOverride = () =>
  useRefreshingMutation((args: { doctorId: number; date: string; acknowledge: boolean }) =>
    api.deleteOverride(args.doctorId, args.date, args.acknowledge),
  );

export const useBookSeries = () =>
  useRefreshingMutation((body: SeriesBody) => api.bookSeries(body));

export const useCreateDoctor = () =>
  useRefreshingMutation((body: NewDoctor) => api.createDoctor(body));

export const useDeleteDoctor = () => useRefreshingMutation((id: number) => api.deleteDoctor(id));

export const useJoinWaitlist = () =>
  useRefreshingMutation((args: { doctorId: number; patientId: number; date: string }) =>
    api.joinWaitlist(args.doctorId, args.patientId, args.date),
  );

export const useLeaveWaitlist = () => useRefreshingMutation((id: number) => api.leaveWaitlist(id));

export const useAcceptOffer = () =>
  useRefreshingMutation((args: { id: number; reason: string; depositConfirmed: boolean }) =>
    api.acceptOffer(args.id, args.reason, args.depositConfirmed),
  );

export const useCheckIn = () => useRefreshingMutation((id: number) => api.checkIn(id));

export const useCorrect = () =>
  useRefreshingMutation((args: { id: number; status: Status; note: string }) =>
    api.correct(args.id, args.status, args.note),
  );

export const useUpdatePatient = () =>
  useRefreshingMutation((args: { id: number; changes: PatientChanges }) =>
    api.updatePatient(args.id, args.changes),
  );

export const useDeclineOffer = () => useRefreshingMutation((id: number) => api.declineOffer(id));
