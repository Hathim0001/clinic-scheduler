import { useState } from "react";
import { Link } from "react-router";
import {
  useAcceptOffer,
  useDeclineOffer,
  useDoctorWaitlist,
  useJoinWaitlist,
  useLeaveWaitlist,
  usePatientWaitlist,
  usePolicy,
} from "../api/hooks";
import type { Deposit, WaitlistEntry } from "../api/types";
import { formatDayIST, formatIST, formatTimeIST } from "../lib/formatIST";
import { Banner, ErrorBanner } from "./common";
import { DepositCheckbox } from "./DepositNotice";

/** Shown when a day has no free time: put the patient in the queue for that doctor and date. */
export function JoinWaitlist({
  doctorId,
  patientId,
  date,
}: {
  doctorId: number;
  patientId: number | null;
  date: string;
}) {
  const join = useJoinWaitlist();
  const holdMinutes = usePolicy().data?.offer_hold_minutes ?? 30;
  return (
    <div>
      <p className="muted">
        Or join the waitlist for this day: if a booking is cancelled, the first patient in the queue
        who can take the slot is offered it for {holdMinutes} minutes.
      </p>
      <button
        type="button"
        disabled={patientId === null || join.isPending}
        onClick={() => patientId !== null && join.mutate({ doctorId, patientId, date })}
      >
        Join the waitlist for {formatDayIST(`${date}T12:00:00+05:30`)}
      </button>
      {patientId === null && <p className="muted">Choose a patient first.</p>}
      {join.error && <ErrorBanner error={join.error} />}
      {join.data && (
        <Banner kind="success">
          {join.data.patient_name} is number {join.data.position} in the queue.{" "}
          <Link to={`/patients/${join.data.patient_id}`}>See offers</Link>
        </Banner>
      )}
    </div>
  );
}

/** The queue for one doctor and date, for the day view. */
export function DayWaitlist({ doctorId, date }: { doctorId: number; date: string }) {
  const queue = useDoctorWaitlist(doctorId, date);
  if (!queue.data || queue.data.length === 0) return null;
  return (
    <section className="card" aria-label="Waitlist">
      <h2>Waitlist</h2>
      <ol>
        {queue.data.map((entry) => (
          <li key={entry.id}>
            <Link to={`/patients/${entry.patient_id}`}>{entry.patient_name}</Link>{" "}
            {entry.status === "OFFERED" && entry.offered_start_at_ist
              ? `holds an offer for ${formatTimeIST(entry.offered_start_at_ist)}`
              : "waiting"}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Offer({ entry, deposit }: { entry: WaitlistEntry; deposit: Deposit | null }) {
  const accept = useAcceptOffer();
  const decline = useDeclineOffer();
  const leave = useLeaveWaitlist();
  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const needsDeposit = deposit?.required === true;
  return (
    <div className="card" aria-label={`Offer ${entry.id}`}>
      <p>
        <strong>
          Slot offered: {entry.offered_start_at_ist && formatIST(entry.offered_start_at_ist)}
        </strong>{" "}
        with {entry.doctor_name}
        {entry.offer_expires_at_ist &&
          ` (hold ends ${formatTimeIST(entry.offer_expires_at_ist)} IST)`}
      </p>
      <label>
        Reason for the visit
        <input value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} />
      </label>
      {deposit && needsDeposit && (
        <DepositCheckbox deposit={deposit} checked={acknowledged} onChange={setAcknowledged} />
      )}
      <div className="actions">
        <button
          type="button"
          className="primary"
          disabled={reason.trim() === "" || (needsDeposit && !acknowledged) || accept.isPending}
          onClick={() =>
            accept.mutate({
              id: entry.id,
              reason,
              depositConfirmed: needsDeposit && acknowledged,
            })
          }
        >
          Accept and book
        </button>
        <button type="button" disabled={decline.isPending} onClick={() => decline.mutate(entry.id)}>
          Not this one (keep my place)
        </button>
        <button type="button" disabled={leave.isPending} onClick={() => leave.mutate(entry.id)}>
          Leave the waitlist
        </button>
      </div>
      {accept.error && <ErrorBanner error={accept.error} />}
    </div>
  );
}

/** A patient's waitlist entries, with any open offer ready to accept. */
export function PatientWaitlist({
  patientId,
  deposit,
}: {
  patientId: number;
  deposit: Deposit | null;
}) {
  const entries = usePatientWaitlist(patientId);
  const leave = useLeaveWaitlist();
  if (!entries.data || entries.data.length === 0) return null;
  return (
    <section aria-label="Waitlist">
      <h2>Waitlist</h2>
      {entries.data.map((entry) =>
        entry.status === "OFFERED" ? (
          <Offer key={entry.id} entry={entry} deposit={deposit} />
        ) : (
          <p key={entry.id}>
            Waiting for {entry.doctor_name} on {formatDayIST(`${entry.date}T12:00:00+05:30`)}
            {entry.position !== null && ` (number ${entry.position} in the queue)`}{" "}
            <button type="button" disabled={leave.isPending} onClick={() => leave.mutate(entry.id)}>
              Leave the waitlist
            </button>
          </p>
        ),
      )}
      {leave.error && <ErrorBanner error={leave.error} />}
    </section>
  );
}
