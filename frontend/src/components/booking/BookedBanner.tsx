import { Link } from "react-router";
import type { Appointment } from "../../api/types";
import { formatIST, istDate } from "../../lib/formatIST";
import { Banner } from "../common";

export function BookedBanner({ result, more }: { result: Appointment; more: number }) {
  return (
    <Banner kind="success">
      Booked: {result.patient_name} with {result.doctor_name} on {formatIST(result.start_at_ist)}
      {more > 0 ? ` and ${more} more` : ""}.{" "}
      <Link to={`/day?doctor=${result.doctor_id}&date=${istDate(result.start_at_ist)}`}>
        See the day
      </Link>
    </Banner>
  );
}
