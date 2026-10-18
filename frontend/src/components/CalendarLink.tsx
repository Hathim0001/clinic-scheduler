import { DownloadButton } from "./DownloadButton";

/** Download an appointment, or a patient's upcoming ones, as a calendar (.ics) file. */
export function CalendarLink({
  path,
  label = "Add to calendar",
}: {
  path: string;
  label?: string;
}) {
  return <DownloadButton path={path} fallbackName="appointment.ics" label={label} />;
}
