import { usePolicy } from "../api/hooks";
import type { Deposit } from "../api/types";
import { formatIST } from "../lib/formatIST";
import { Banner } from "./common";

const KIND_TEXT = { NO_SHOW: "No-show", LATE_CANCELLED: "Late cancellation" } as const;

/** Explains why a patient is flagged: the strikes in the clinic's look-back period and when the flag ends. */
export function DepositExplanation({ deposit }: { deposit: Deposit }) {
  const days = usePolicy().data?.strike_lookback_days ?? 30;
  const strikes = usePolicy().data?.strikes ?? 2;
  if (deposit.reasons.length === 0) {
    return <p className="muted">No late cancellations or no-shows in the last {days} days.</p>;
  }
  return (
    <div>
      <p>
        {deposit.required ? (
          <strong>
            Deposit required
            {deposit.required_until_ist ? ` until ${formatIST(deposit.required_until_ist)}` : ""}.
          </strong>
        ) : (
          <span>
            {deposit.reasons.length} so far: a deposit is only required from {strikes}.
          </span>
        )}
      </p>
      <ul>
        {deposit.reasons.map((strike) => (
          <li key={strike.appointment_id}>
            {KIND_TEXT[strike.type]} on {formatIST(strike.at_ist)} (appointment #
            {strike.appointment_id})
          </li>
        ))}
      </ul>
    </div>
  );
}

interface Props {
  deposit: Deposit;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

/** The deposit checkbox. It only exists for a flagged patient, and its label says why. */
export function DepositCheckbox({ deposit, checked, onChange }: Props) {
  if (!deposit.required) return null;
  return (
    <Banner kind="warn">
      <DepositExplanation deposit={deposit} />
      <label className="check">
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>
          The patient has acknowledged the deposit
          {deposit.required_until_ist
            ? ` (applies until ${formatIST(deposit.required_until_ist)})`
            : ""}
        </span>
      </label>
    </Banner>
  );
}
