interface Props {
  repeat: boolean;
  onRepeat: (value: boolean) => void;
  everyDays: number;
  onEveryDays: (value: number) => void;
  count: number;
  onCount: (value: number) => void;
}

/** "Repeat this appointment": a series at the same time of day, all booked or none. */
export function RepeatFields({ repeat, onRepeat, everyDays, onEveryDays, count, onCount }: Props) {
  return (
    <>
      <label className="check">
        <input type="checkbox" checked={repeat} onChange={(e) => onRepeat(e.target.checked)} />
        Repeat this appointment
      </label>
      {repeat && (
        <div className="row">
          <label>
            Every (days)
            <input
              type="number"
              min={1}
              max={60}
              value={everyDays}
              onChange={(e) => onEveryDays(Number(e.target.value))}
            />
          </label>
          <label>
            Number of appointments
            <input
              type="number"
              min={2}
              max={12}
              value={count}
              onChange={(e) => onCount(Number(e.target.value))}
            />
          </label>
          <p className="muted">
            Same time of day. Every date must be free, or none of them is booked.
          </p>
        </div>
      )}
    </>
  );
}
