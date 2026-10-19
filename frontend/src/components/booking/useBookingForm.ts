import { useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import {
  useAppointment,
  useBook,
  useBookSeries,
  useDoctors,
  usePatient,
  useReschedule,
  useSlots,
} from "../../api/hooks";
import { istDate } from "../../lib/formatIST";
import { readLastPatient, rememberPatient } from "../../lib/lastPatient";
import { useToday } from "../../lib/useToday";
import type { Mover } from "./RescheduleNotices";

/**
 * Everything the booking page decides, kept out of the markup: which doctor, day, patient and
 * length are in play, which starts the server offers, whether the form is ready, and what
 * submitting sends. What the person picked overrides what the link or the original suggests.
 */
export function useBookingForm() {
  const [params] = useSearchParams();
  const rescheduleId = Number(params.get("reschedule")) || null;
  const original = useAppointment(rescheduleId);
  const doctors = useDoctors();
  const today = useToday();

  const [pickedDoctor, setPickedDoctor] = useState<number | null>(null);
  const [pickedDate, setPickedDate] = useState<string | null>(null);
  // Start with the patient of the last booking, unless a link or a move names one.
  const [remembered] = useState(() => (params.get("patient") ? null : readLastPatient()));
  const [pickedPatient, setPickedPatient] = useState<number | null>(
    Number(params.get("patient")) || remembered,
  );
  const [pickedStart, setPickedStart] = useState<string | null>(params.get("start"));
  const [reason, setReason] = useState("");
  const [depositAcknowledged, setDepositAcknowledged] = useState(false);
  const [repeat, setRepeat] = useState(false);
  const [everyDays, setEveryDays] = useState(7);
  const [count, setCount] = useState(4);
  const [visitSlots, setVisitSlots] = useState(1);
  const [mover, setMover] = useState<Mover>("PATIENT");

  const doctorId =
    pickedDoctor ??
    (Number(params.get("doctor")) || original.data?.doctor_id || doctors.data?.[0]?.id || null);
  const date =
    pickedDate ??
    params.get("date") ??
    (original.data ? istDate(original.data.start_at_ist) : today);
  const patientId = rescheduleId ? (original.data?.patient_id ?? null) : pickedPatient;

  const patient = usePatient(patientId);
  const doctor = doctors.data?.find((d) => d.id === doctorId);
  // A moved visit keeps its length in minutes: that is a whole number of this doctor's slots or it
  // cannot be moved to them. A new booking uses the length the person chose.
  const movedMinutes = original.data?.duration_min ?? null;
  const lengthInSlots =
    rescheduleId !== null && movedMinutes !== null && doctor
      ? movedMinutes % doctor.slot_length_min === 0
        ? movedMinutes / doctor.slot_length_min
        : null
      : visitSlots;
  const slots = useSlots(doctorId, date, patientId ?? undefined, lengthInSlots ?? 1);
  const book = useBook();
  const reschedule = useReschedule();
  const series = useBookSeries();
  // One key per distinct booking attempt: pressing the button again after a lost answer sends the
  // same key, so the server returns the first appointment instead of booking twice.
  const attempt = useRef<{ signature: string; key: string } | null>(null);

  const offered = lengthInSlots === null ? [] : (slots.data?.slots ?? []);
  const start =
    pickedStart && offered.some((slot) => slot.start_at_ist === pickedStart) ? pickedStart : null;
  const deposit = patient.data?.deposit ?? null;
  const depositRequired = deposit?.required === true;

  const ready =
    doctorId !== null &&
    patientId !== null &&
    start !== null &&
    lengthInSlots !== null &&
    (rescheduleId !== null || reason.trim() !== "") &&
    (!depositRequired || depositAcknowledged);

  const move = (acknowledgeLate: boolean) => {
    if (rescheduleId === null || doctorId === null || start === null) return;
    reschedule.mutate({
      id: rescheduleId,
      body: {
        start_at: start,
        doctor_id: doctorId,
        by: mover,
        ...(acknowledgeLate ? { acknowledge_late: true } : {}),
        ...(depositRequired ? { deposit_confirmed: depositAcknowledged } : {}),
      },
    });
  };

  const bookOne = (doctor_id: number, patient_id: number, start_at: string) => {
    const signature = JSON.stringify([
      doctor_id,
      patient_id,
      start_at,
      reason,
      depositAcknowledged,
      visitSlots,
    ]);
    if (attempt.current?.signature !== signature) {
      attempt.current = {
        signature,
        key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
      };
    }
    book.mutate(
      {
        doctor_id,
        patient_id,
        start_at,
        reason,
        deposit_confirmed: depositRequired && depositAcknowledged,
        slots: visitSlots,
        idempotencyKey: attempt.current.key,
      },
      { onSuccess: () => rememberPatient(patient_id) },
    );
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready || doctorId === null || patientId === null || start === null) return;
    if (rescheduleId !== null) return move(false);
    if (!repeat) return bookOne(doctorId, patientId, start);
    series.mutate(
      {
        doctor_id: doctorId,
        patient_id: patientId,
        start_at: start,
        reason,
        deposit_confirmed: depositRequired && depositAcknowledged,
        slots: visitSlots,
        every_days: everyDays,
        count,
      },
      { onSuccess: () => rememberPatient(patientId) },
    );
  };

  return {
    rescheduleId,
    original,
    doctors,
    doctor,
    doctorId,
    date,
    patientId,
    patientFromLastBooking: remembered !== null && pickedPatient === remembered,
    patient,
    deposit,
    movedMinutes,
    lengthInSlots,
    slots,
    offered,
    start,
    ready,
    submit,
    move,
    reschedule,
    result: book.data ?? series.data?.appointments[0] ?? reschedule.data?.new ?? null,
    seriesLength: series.data?.appointments.length ?? 0,
    error: book.error ?? series.error ?? reschedule.error,
    pending: book.isPending || series.isPending || reschedule.isPending,
    fields: {
      reason,
      setReason,
      depositAcknowledged,
      setDepositAcknowledged,
      repeat,
      setRepeat,
      everyDays,
      setEveryDays,
      count,
      setCount,
      visitSlots,
      setVisitSlots,
      mover,
      setMover,
      setPickedDoctor,
      setPickedDate,
      setPickedPatient,
      setPickedStart,
    },
  };
}
