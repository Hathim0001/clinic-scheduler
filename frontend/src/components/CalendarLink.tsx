import { API_BASE } from "../api/client";

/** A plain download link: the server sends the .ics file, so there is nothing to fetch here. */
export function CalendarLink({
  path,
  label = "Add to calendar",
}: {
  path: string;
  label?: string;
}) {
  return (
    <a href={`${API_BASE}${path}`} download>
      {label}
    </a>
  );
}
