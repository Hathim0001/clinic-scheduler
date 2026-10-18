import type { TimeWindow } from "../../api/types";

const TIME_PATTERN = "([01][0-9]|2[0-3]):[0-5][0-9]|24:00";

export function WindowFields({
  label,
  window,
  onChange,
  onRemove,
}: {
  label: string;
  window: TimeWindow;
  onChange: (next: TimeWindow) => void;
  onRemove: () => void;
}) {
  return (
    <div className="window-row">
      <label>
        <span className="visually-hidden">{label} from</span>
        <input
          aria-label={`${label} from`}
          value={window.start}
          pattern={TIME_PATTERN}
          placeholder="09:00"
          size={6}
          onChange={(event) => onChange({ ...window, start: event.target.value })}
        />
      </label>
      <span className="muted">to</span>
      <label>
        <span className="visually-hidden">{label} to</span>
        <input
          aria-label={`${label} to`}
          value={window.end}
          pattern={TIME_PATTERN}
          placeholder="13:00"
          size={6}
          onChange={(event) => onChange({ ...window, end: event.target.value })}
        />
      </label>
      <button type="button" className="small" onClick={onRemove} aria-label={`Remove ${label}`}>
        Remove
      </button>
    </div>
  );
}
