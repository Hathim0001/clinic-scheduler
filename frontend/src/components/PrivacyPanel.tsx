import { useState } from "react";
import { useErasePatient, useRecordConsent } from "../api/hooks";
import type { Patient } from "../api/types";
import { formatIST } from "../lib/formatIST";
import { Banner, ErrorBanner } from "./common";

/**
 * Consent and erasure for one patient (India's DPDP Act). Erasing replaces the name, phone, date of
 * birth and visit reasons for good, so it asks twice and says what stays behind.
 */
export function PrivacyPanel({ patient }: { patient: Patient }) {
  const consent = useRecordConsent();
  const erase = useErasePatient();
  const [confirming, setConfirming] = useState(false);

  if (patient.erased) {
    return (
      <section className="card" aria-label="Privacy">
        <h2>Privacy</h2>
        <Banner kind="info">
          This patient&apos;s personal data was erased on request. Their appointments remain as
          anonymous history.
        </Banner>
      </section>
    );
  }

  return (
    <section className="card" aria-label="Privacy">
      <h2>Privacy</h2>
      <p>
        {patient.consent_at_utc
          ? `Accepted the privacy notice on ${formatIST(patient.consent_at_utc)}.`
          : "The patient's acceptance of the privacy notice has not been recorded."}{" "}
        <button
          type="button"
          onClick={() => consent.mutate(patient.id)}
          disabled={consent.isPending}
        >
          {patient.consent_at_utc ? "Record again" : "Record consent"}
        </button>
      </p>
      {consent.error && <ErrorBanner error={consent.error} />}

      {!confirming ? (
        <button type="button" onClick={() => setConfirming(true)}>
          Erase this patient&apos;s data…
        </button>
      ) : (
        <Banner kind="warn">
          <p>
            This replaces the name, phone, date of birth and visit reasons with blanks and cannot be
            undone. Past appointments stay, without anything that identifies the patient. It is
            refused while the patient has an upcoming appointment or a waitlist place.
          </p>
          <div className="actions">
            <button
              type="button"
              className="danger"
              onClick={() => erase.mutate(patient.id)}
              disabled={erase.isPending}
            >
              Erase permanently
            </button>
            <button type="button" onClick={() => setConfirming(false)}>
              Keep the data
            </button>
          </div>
        </Banner>
      )}
      {erase.error && <ErrorBanner error={erase.error} />}
    </section>
  );
}
