import { useState, type FormEvent } from "react";
import { useClockInfo } from "../api/hooks";
import { useTestClock } from "../lib/clock";
import { formatIST, isoToIstInput, istInputToIso } from "../lib/formatIST";
import { ErrorBanner } from "./common";

/**
 * Shows the time the server is using and, when the server allows it, lets a reviewer set a test
 * clock (India time) so the booking-window, cancellation and deposit rules can be tried on any date.
 */
export function ClockBar() {
  const { testClock, setTestClock, clearTestClock } = useTestClock();
  const info = useClockInfo();
  const [draft, setDraft] = useState(() => (testClock ? isoToIstInput(testClock) : ""));
  const seedDay = info.data?.seed_queue_day ?? null;

  const apply = (event: FormEvent) => {
    event.preventDefault();
    if (draft) setTestClock(istInputToIso(draft));
  };

  return (
    <section className="clock-bar" aria-label="Clock">
      {testClock && (
        <span className="test-clock-badge">TEST CLOCK ACTIVE: {formatIST(testClock)}</span>
      )}
      {info.data && (
        <span className="clock-note">
          Server time {formatIST(info.data.now_utc)} (
          {info.data.source === "HEADER" ? "test" : "real"} clock)
        </span>
      )}
      {info.data?.test_clock_enabled && (
        <form className="row" onSubmit={apply}>
          <label>
            <span className="visually-hidden">Test clock, India time</span>
            <input
              type="datetime-local"
              aria-label="Test clock (India time)"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
            />
          </label>
          <button type="submit" disabled={!draft}>
            Set clock
          </button>
          {seedDay && (
            <button type="button" onClick={() => setTestClock(`${seedDay}T09:30:00+05:30`)}>
              Seed day 09:30
            </button>
          )}
        </form>
      )}
      {testClock && (
        <button type="button" onClick={clearTestClock}>
          Use the real time
        </button>
      )}
      {info.error && <ErrorBanner error={info.error} />}
    </section>
  );
}
