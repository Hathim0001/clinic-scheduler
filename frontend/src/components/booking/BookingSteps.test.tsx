import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BookingSteps } from "./BookingSteps";

describe("the booking steps", () => {
  it("tick what is done and mark the first open step as current", () => {
    render(
      <BookingSteps
        steps={[
          { label: "Patient", done: true },
          { label: "Doctor and date", done: false },
          { label: "Time", done: false },
        ]}
      />,
    );
    const list = screen.getByRole("list", { name: "Booking progress" });
    const items = list.querySelectorAll("li");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Patient (done)");
    expect(items[1]).toHaveAttribute("aria-current", "step");
    expect(items[2]).not.toHaveAttribute("aria-current");
  });

  it("marks nothing current once every step is done", () => {
    render(<BookingSteps steps={[{ label: "Patient", done: true }]} />);
    expect(document.querySelector("[aria-current]")).toBeNull();
  });
});
