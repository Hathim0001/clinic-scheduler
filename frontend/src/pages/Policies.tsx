import { useState, type FormEvent } from "react";
import { useDelivery, usePolicy, useUpdatePolicy } from "../api/hooks";
import type { Policy, PolicyField } from "../api/types";
import { Banner, ErrorBanner, Skeleton } from "../components/common";
import { useIsAdmin } from "../components/AuthGate";
import { PageHeader } from "../components/ui";
import { formatIST } from "../lib/formatIST";

interface Rule {
  name: PolicyField;
  label: string;
  unit: string;
  describe: (value: number, all: Record<PolicyField, number>) => string;
}

interface Group {
  title: string;
  intro: string;
  rules: Rule[];
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

const GROUPS: Group[] = [
  {
    title: "Booking",
    intro: "How far ahead the clinic takes bookings.",
    rules: [
      {
        name: "horizon_days",
        label: "Bookings open up to",
        unit: "days ahead",
        describe: (v) => `Visits can be booked up to ${plural(v, "day")} ahead.`,
      },
    ],
  },
  {
    title: "Cancellations",
    intro: "What counts as a late cancellation, and how long a cancellation can be taken back.",
    rules: [
      {
        name: "late_cancel_hours",
        label: "A cancellation counts as late when it is less than",
        unit: "hours before the visit",
        describe: (v) =>
          v === 0
            ? "Only a cancellation after the visit has started counts as late."
            : `A patient who cancels less than ${plural(v, "hour")} before the visit has cancelled late.`,
      },
      {
        name: "undo_minutes",
        label: "A cancellation can be undone for",
        unit: "minutes",
        describe: (v) =>
          v === 0
            ? "Cancellations cannot be undone."
            : `Reception can take a cancellation back for ${plural(v, "minute")}, if the slot is still free.`,
      },
    ],
  },
  {
    title: "Deposit rule",
    intro: "When a patient who has missed visits must acknowledge a deposit before booking again.",
    rules: [
      {
        name: "strikes",
        label: "Late cancellations or no-shows that trigger it",
        unit: "times",
        describe: (v, all) =>
          `A patient with ${plural(v, "late cancellation or no-show", "late cancellations or no-shows")} in the last ${plural(all.strike_lookback_days, "day")} must acknowledge a deposit when booking.`,
      },
      {
        name: "strike_lookback_days",
        label: "Counted over the last",
        unit: "days",
        describe: (v) =>
          `Older late cancellations and no-shows are forgotten after ${plural(v, "day")}.`,
      },
    ],
  },
  {
    title: "Waitlist",
    intro: "What happens when a booked slot is freed.",
    rules: [
      {
        name: "offer_hold_minutes",
        label: "A freed slot is held for the next person for",
        unit: "minutes",
        describe: (v) => `The patient offered a slot has ${plural(v, "minute")} to take it.`,
      },
    ],
  },
  {
    title: "Reminders",
    intro: "When patients are reminded of a visit. Set a time to 0 to switch that reminder off.",
    rules: [
      {
        name: "reminder_first_hours",
        label: "First reminder",
        unit: "hours before",
        describe: (v) =>
          v === 0 ? "No first reminder." : `Sent ${plural(v, "hour")} before the visit.`,
      },
      {
        name: "reminder_second_hours",
        label: "Second reminder",
        unit: "hours before",
        describe: (v) =>
          v === 0 ? "No second reminder." : `Sent ${plural(v, "hour")} before the visit.`,
      },
    ],
  },
];

const FIELD_NAMES: PolicyField[] = GROUPS.flatMap((g) => g.rules.map((r) => r.name));

type Values = Record<PolicyField, string>;

const toValues = (policy: Pick<Policy, PolicyField>): Values =>
  Object.fromEntries(FIELD_NAMES.map((name) => [name, String(policy[name])])) as Values;

function DeliveryNote() {
  const delivery = useDelivery();
  if (!delivery.data) return null;
  const { gateway, channel } = delivery.data;
  return (
    <p className="muted">
      {gateway === null
        ? "No message gateway is connected, so reminders wait on the Messages page for reception to send by hand."
        : `Reminders are sent automatically through ${
            gateway === "twilio"
              ? `Twilio ${channel === "whatsapp" ? "WhatsApp" : "SMS"}`
              : "the connected gateway"
          }.`}
    </p>
  );
}

/** The clinic's own rules. Everyone can read them; an administrator can change them. */
export default function Policies() {
  const policy = usePolicy();
  const isAdmin = useIsAdmin();
  const update = useUpdatePolicy();
  const [draft, setDraft] = useState<Values | null>(null);
  const [saved, setSaved] = useState(false);

  if (policy.isPending) return <Skeleton rows={4} />;
  if (policy.error) {
    return <ErrorBanner error={policy.error} onRetry={() => void policy.refetch()} />;
  }
  const current = policy.data;
  const values = draft ?? toValues(current);
  const numbers = Object.fromEntries(
    FIELD_NAMES.map((name) => [name, Number(values[name])]),
  ) as Record<PolicyField, number>;
  const changed = FIELD_NAMES.filter((name) => numbers[name] !== current[name]);
  const outOfRange = FIELD_NAMES.filter((name) => {
    const [low, high] = current.bounds[name];
    const n = numbers[name];
    return !Number.isInteger(n) || values[name].trim() === "" || n < low || n > high;
  });

  const setValue = (name: PolicyField, value: string) => {
    setSaved(false);
    setDraft({ ...values, [name]: value });
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const changes = Object.fromEntries(changed.map((name) => [name, numbers[name]]));
    update.mutate(changes, {
      onSuccess: () => {
        setDraft(null);
        setSaved(true);
      },
    });
  };

  return (
    <div>
      <PageHeader
        title="Clinic rules"
        description="The numbers behind booking, cancelling and reminders. A change applies from now on; visits that are already booked are never rewritten."
      />
      {!isAdmin && <Banner kind="info">Only an administrator can change these rules.</Banner>}
      <form onSubmit={submit} aria-label="Clinic rules">
        {GROUPS.map((group) => (
          <section key={group.title} className="card panel" aria-labelledby={`g-${group.title}`}>
            <div className="panel-head">
              <h2 id={`g-${group.title}`}>{group.title}</h2>
            </div>
            <p className="muted">{group.intro}</p>
            {group.title === "Reminders" && <DeliveryNote />}
            <div className="rules">
              {group.rules.map((rule) => {
                const [low, high] = current.bounds[rule.name];
                const wrong = outOfRange.includes(rule.name);
                const helpId = `help-${rule.name}`;
                return (
                  <div key={rule.name} className="rule">
                    <label>
                      {rule.label}
                      <span className="rule-input">
                        <input
                          type="number"
                          inputMode="numeric"
                          min={low}
                          max={high}
                          step={1}
                          value={values[rule.name]}
                          disabled={!isAdmin}
                          aria-describedby={helpId}
                          aria-invalid={wrong}
                          onChange={(event) => setValue(rule.name, event.target.value)}
                        />
                        <span className="rule-unit">{rule.unit}</span>
                      </span>
                    </label>
                    <p id={helpId} className={wrong ? "rule-help rule-wrong" : "rule-help"}>
                      {wrong
                        ? `Use a whole number from ${low} to ${high}.`
                        : rule.describe(numbers[rule.name], numbers)}
                    </p>
                  </div>
                );
              })}
            </div>
          </section>
        ))}

        {update.error && <ErrorBanner error={update.error} />}
        {saved && (
          <Banner kind="success">
            Rules saved. They apply to bookings, cancellations and reminders from now on.
          </Banner>
        )}
        {isAdmin && (
          <div className="actions">
            <button
              type="submit"
              className="primary"
              disabled={update.isPending || changed.length === 0 || outOfRange.length > 0}
            >
              {update.isPending ? "Saving…" : "Save rules"}
            </button>
            <button
              type="button"
              onClick={() => {
                setSaved(false);
                setDraft(toValues(current.defaults));
              }}
              disabled={FIELD_NAMES.every(
                (name) => String(current.defaults[name]) === values[name],
              )}
            >
              Use the standard values
            </button>
          </div>
        )}
      </form>
      <p className="muted">
        {current.updated_at_utc
          ? `Last changed ${formatIST(current.updated_at_utc)}${current.updated_by ? ` by ${current.updated_by}` : ""}.`
          : "These are the standard values; nobody has changed them."}
      </p>
    </div>
  );
}
