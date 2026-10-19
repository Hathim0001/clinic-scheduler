import { Icon } from "../ui";

export interface Step {
  label: string;
  done: boolean;
}

/**
 * Where the person is in the booking: the steps in order, each ticked once it is filled in, the
 * first one still open marked as the current step. It repeats the headings below as a map; the
 * form itself is unchanged.
 */
export function BookingSteps({ steps }: { steps: Step[] }) {
  const current = steps.findIndex((step) => !step.done);
  return (
    <ol className="steps" aria-label="Booking progress">
      {steps.map((step, index) => (
        <li
          key={step.label}
          className={step.done ? "step done" : index === current ? "step current" : "step"}
          aria-current={index === current ? "step" : undefined}
        >
          <span className="step-mark" aria-hidden="true">
            {step.done ? <Icon name="check" size={14} /> : index + 1}
          </span>
          <span className="step-label">
            {step.label}
            {step.done && <span className="visually-hidden"> (done)</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}
