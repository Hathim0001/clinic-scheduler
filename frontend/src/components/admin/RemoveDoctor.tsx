import { useState } from "react";
import { useDeleteDoctor } from "../../api/hooks";
import type { Doctor } from "../../api/types";
import { ErrorBanner } from "../common";

export function RemoveDoctor({ doctor, onRemoved }: { doctor: Doctor; onRemoved: () => void }) {
  const remove = useDeleteDoctor();
  const [confirming, setConfirming] = useState(false);
  return (
    <section className="card" aria-label="Remove doctor">
      <h2>Remove this doctor</h2>
      <p className="muted">
        Only possible while the doctor has no appointments on record, past or future. Their hours
        and leave are deleted with them.
      </p>
      {!confirming ? (
        <button type="button" onClick={() => setConfirming(true)}>
          Remove {doctor.name}
        </button>
      ) : (
        <div className="actions">
          <button
            type="button"
            className="danger"
            disabled={remove.isPending}
            onClick={() => remove.mutate(doctor.id, { onSuccess: onRemoved })}
          >
            Yes, remove {doctor.name}
          </button>
          <button type="button" onClick={() => setConfirming(false)}>
            Keep
          </button>
        </div>
      )}
      {remove.error && <ErrorBanner error={remove.error} />}
    </section>
  );
}

// ------------------------------------------------------------------------------- details
