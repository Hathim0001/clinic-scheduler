import type { Doctor } from "../../api/types";
import { OverrideForm } from "./OverrideForm";
import { OverrideList } from "./OverrideList";

export function Overrides({ doctor }: { doctor: Doctor }) {
  return (
    <section className="card" aria-label="Date overrides">
      <h2>Leave and special hours</h2>
      <p className="muted">
        A date override replaces the weekly hours for that one date. Leave means not working. Hours
        on a day the doctor does not normally work add an extra working day.
      </p>
      <OverrideForm doctor={doctor} />
      <OverrideList doctor={doctor} />
    </section>
  );
}
