import { useState } from "react";
import { useDelivery, useMarkMessageSent, useMessages, useRunReminders } from "../api/hooks";
import type { Message, MessageStatus } from "../api/types";
import { useIsAdmin } from "../components/AuthGate";
import { Banner, ErrorBanner, Skeleton } from "../components/common";
import { PageHeader } from "../components/ui";
import { formatIST } from "../lib/formatIST";

const FILTERS: { value: MessageStatus | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "PENDING", label: "Waiting to send" },
  { value: "SKIPPED", label: "Phone the patient" },
  { value: "FAILED", label: "Failed" },
  { value: "SENT", label: "Sent" },
];

const STATUS_TEXT: Record<MessageStatus, string> = {
  PENDING: "Waiting to send",
  SKIPPED: "Phone the patient",
  FAILED: "Failed",
  SENT: "Sent",
};

const hoursText = (hours: number) => (hours === 0 ? "off" : `${hours} h before`);

/** How messages leave the clinic, the reminder times, and what is waiting. */
function DeliveryPanel() {
  const delivery = useDelivery();
  const run = useRunReminders();
  const isAdmin = useIsAdmin();
  if (!delivery.data) return null;
  const { gateway, channel, counts } = delivery.data;
  const how =
    gateway === null
      ? "By hand: no gateway is connected, so reception sends each message."
      : `Automatically through ${
          gateway === "twilio"
            ? `Twilio ${channel === "whatsapp" ? "WhatsApp" : "SMS"}`
            : "the connected gateway"
        }.`;
  return (
    <section className="card panel" aria-labelledby="delivery-heading">
      <div className="panel-head">
        <h2 id="delivery-heading">How messages are sent</h2>
      </div>
      <p>{how}</p>
      <dl className="delivery">
        <dt>Reminders</dt>
        <dd>
          first {hoursText(delivery.data.reminder_first_hours)}, second{" "}
          {hoursText(delivery.data.reminder_second_hours)}
        </dd>
        <dt>Waiting to send</dt>
        <dd>{counts.PENDING ?? 0}</dd>
        <dt>Phone the patient</dt>
        <dd>{counts.SKIPPED ?? 0}</dd>
        <dt>Failed</dt>
        <dd>{counts.FAILED ?? 0}</dd>
        <dt>Reminders sent</dt>
        <dd>{counts.reminders_sent ?? 0}</dd>
      </dl>
      {isAdmin && (
        <div className="actions">
          <button type="button" onClick={() => run.mutate()} disabled={run.isPending}>
            {run.isPending ? "Checking…" : "Queue due reminders now"}
          </button>
        </div>
      )}
      {run.error && <ErrorBanner error={run.error} />}
      {run.data && (
        <Banner kind="success">
          {run.data.queued === 0
            ? "No reminder is due right now."
            : `${run.data.queued} ${run.data.queued === 1 ? "reminder was" : "reminders were"} queued.`}
        </Banner>
      )}
    </section>
  );
}

/**
 * Messages the system wrote for patients (confirmations, a clinic cancellation or move, a waitlist
 * offer). With a gateway configured they are sent by the server; without one they wait here and
 * reception phones the patient and marks each one sent. A patient with no recorded consent is never
 * messaged by the gateway: that message says to phone instead.
 */
export default function Messages() {
  const [status, setStatus] = useState<MessageStatus | "">("");
  const [shown, setShown] = useState(20);
  const messages = useMessages(status || undefined, shown);

  return (
    <div>
      <PageHeader
        title="Messages to patients"
        description="Confirmations, changes and reminders. Patients whose consent to the privacy notice is not recorded are never messaged by the server: phone them instead."
      />
      <DeliveryPanel />
      <div className="row">
        <label>
          Show
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as MessageStatus | "");
              setShown(20);
            }}
          >
            {FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {messages.isPending && <Skeleton rows={3} />}
      {messages.error && (
        <ErrorBanner error={messages.error} onRetry={() => void messages.refetch()} />
      )}
      {messages.data && messages.data.items.length === 0 && (
        <Banner kind="info">No messages here.</Banner>
      )}
      {messages.data && messages.data.items.length > 0 && (
        <div className="table-scroll" role="region" aria-label="Messages" tabIndex={0}>
          <table className="stack">
            <caption className="visually-hidden">Messages to patients, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Written</th>
                <th scope="col">To</th>
                <th scope="col">Message</th>
                <th scope="col">Status</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {messages.data.items.map((message) => (
                <MessageRow key={message.id} message={message} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {messages.data && messages.data.total > messages.data.items.length && (
        <p>
          <button type="button" onClick={() => setShown((n) => Math.min(n + 20, 100))}>
            Show more ({messages.data.items.length} of {messages.data.total})
          </button>
        </p>
      )}
    </div>
  );
}

function MessageRow({ message }: { message: Message }) {
  const mark = useMarkMessageSent();
  const open =
    message.status === "PENDING" || message.status === "SKIPPED" || message.status === "FAILED";
  return (
    <tr>
      <td data-label="Written">{formatIST(message.created_at_utc)}</td>
      <td data-label="To">{message.to_phone}</td>
      <td data-label="Message">
        {message.kind.startsWith("REMINDER") && <span className="chip">Reminder </span>}{" "}
        {message.body}
      </td>
      <td data-label="Status">
        {STATUS_TEXT[message.status as MessageStatus]}
        {message.last_error && message.status !== "SENT" && (
          <span className="muted"> ({message.last_error})</span>
        )}
        {message.status === "SENT" && message.sent_at_utc && (
          <span className="muted">
            {" "}
            {message.sent_via === "MANUAL" ? "by hand" : "by the gateway"},{" "}
            {formatIST(message.sent_at_utc)}
          </span>
        )}
      </td>
      <td data-label="Action">
        {open && (
          <button type="button" onClick={() => mark.mutate(message.id)} disabled={mark.isPending}>
            Mark as sent
          </button>
        )}
        {mark.error && <ErrorBanner error={mark.error} />}
      </td>
    </tr>
  );
}
