import type { Bucket, DayTrend } from "../api/types";

/**
 * Small charts drawn with plain markup: no chart library, nothing to load. Each is a picture with a
 * spoken summary (role="img") and the same numbers as a table for people who read it that way, so
 * the figures are never only a drawing or only a colour.
 */

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const percent = (value: number | null) => (value === null ? "n/a" : `${Math.round(value * 100)}%`);

const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00+05:30`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "Asia/Kolkata",
  });

export const hourLabel = (hour: number) => `${String(hour).padStart(2, "0")}:00`;
export const weekdayLabel = (day: number) => WEEKDAYS[day] ?? String(day);

/** One column per day, stacked by what happened to the visits. */
export function DayChart({ days }: { days: DayTrend[] }) {
  const tallest = Math.max(1, ...days.map((d) => d.scheduled));
  const total = days.reduce((sum, d) => sum + d.scheduled, 0);
  const busiest = days.reduce<DayTrend | null>(
    (best, d) => (best === null || d.scheduled > best.scheduled ? d : best),
    null,
  );
  const summary =
    total === 0
      ? "No visits in this period."
      : `${total} visits over ${days.length} days. Busiest day: ${shortDate(busiest!.date)} with ${busiest!.scheduled}.`;
  const sparse = days.length > 14;

  return (
    <figure className="chart">
      <div className="day-chart" role="img" aria-label={summary}>
        {days.map((d, index) => (
          <div
            key={d.date}
            className="day-col"
            title={`${shortDate(d.date)}: ${d.scheduled} visits, ${d.completed} completed, ${d.no_show} no-shows, ${d.cancelled} cancelled, ${d.upcoming} still booked`}
          >
            <div className="day-stack" aria-hidden="true">
              {(
                [
                  ["bar-upcoming", d.upcoming],
                  ["bar-cancelled", d.cancelled],
                  ["bar-noshow", d.no_show],
                  ["bar-completed", d.completed],
                ] as const
              ).map(([cls, count]) =>
                count > 0 ? (
                  <span
                    key={cls}
                    className={`bar ${cls}`}
                    style={{ height: `${(count / tallest) * 100}%` }}
                  />
                ) : null,
              )}
            </div>
            <span className="day-label" aria-hidden="true">
              {!sparse || index % 7 === 0 || index === days.length - 1 ? shortDate(d.date) : ""}
            </span>
          </div>
        ))}
      </div>
      <ul className="chart-key" aria-label="How to read the chart">
        <li>
          <span className="swatch bar-completed" /> Completed
        </li>
        <li>
          <span className="swatch bar-noshow" /> No-show
        </li>
        <li>
          <span className="swatch bar-cancelled" /> Cancelled
        </li>
        <li>
          <span className="swatch bar-upcoming" /> Still booked
        </li>
      </ul>
      <div className="visually-hidden">
        <table>
          <caption>Visits per day</caption>
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Visits</th>
              <th scope="col">Completed</th>
              <th scope="col">No-shows</th>
              <th scope="col">Cancelled</th>
              <th scope="col">Still booked</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d.date}>
                <th scope="row">{shortDate(d.date)}</th>
                <td>{d.scheduled}</td>
                <td>{d.completed}</td>
                <td>{d.no_show}</td>
                <td>{d.cancelled}</td>
                <td>{d.upcoming}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

/** Horizontal bars of visits for each weekday or hour, with the no-show share marked. */
export function BucketChart({
  buckets,
  label,
  noun,
}: {
  buckets: Bucket[];
  label: (key: number) => string;
  noun: string;
}) {
  const tallest = Math.max(1, ...buckets.map((b) => b.scheduled));
  const known = buckets.filter((b) => b.no_show_rate !== null);
  const worst = known.reduce<Bucket | null>(
    (best, b) => (best === null || (b.no_show_rate ?? 0) > (best.no_show_rate ?? 0) ? b : best),
    null,
  );
  const summary =
    worst && (worst.no_show_rate ?? 0) > 0
      ? `Most missed visits: ${label(worst.key)}, ${percent(worst.no_show_rate)} of those with a known outcome.`
      : "No missed visits in this period.";

  return (
    <figure className="chart">
      <div className="bucket-chart" role="img" aria-label={`Visits by ${noun}. ${summary}`}>
        {buckets.map((b) => (
          <div key={b.key} className="bucket-row" aria-hidden="true">
            <span className="bucket-label">{label(b.key)}</span>
            <span className="bucket-track">
              <span className="bucket-fill" style={{ width: `${(b.scheduled / tallest) * 100}%` }}>
                {b.no_show > 0 && (
                  <span
                    className="bucket-missed"
                    style={{ width: `${(b.no_show / b.scheduled) * 100}%` }}
                  />
                )}
              </span>
            </span>
            <span className="bucket-figure">
              {b.scheduled}
              {b.no_show_rate !== null && b.no_show > 0
                ? ` · ${percent(b.no_show_rate)} missed`
                : ""}
            </span>
          </div>
        ))}
      </div>
      <div className="visually-hidden">
        <table>
          <caption>Visits by {noun}</caption>
          <thead>
            <tr>
              <th scope="col">{noun}</th>
              <th scope="col">Visits</th>
              <th scope="col">Completed</th>
              <th scope="col">No-shows</th>
              <th scope="col">No-show rate</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((b) => (
              <tr key={b.key}>
                <th scope="row">{label(b.key)}</th>
                <td>{b.scheduled}</td>
                <td>{b.completed}</td>
                <td>{b.no_show}</td>
                <td>{percent(b.no_show_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
