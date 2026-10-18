import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ScheduleSlot } from "../api/types";
import { DaySummary } from "./DaySummary";

const slot = (hour: number, state: ScheduleSlot["state"]) =>
  ({
    start_at_ist: `2026-10-19T${String(hour).padStart(2, "0")}:00:00+05:30`,
    end_at_ist: `2026-10-19T${String(hour).padStart(2, "0")}:30:00+05:30`,
    state,
    appointment: null,
  }) as ScheduleSlot;

describe("the day summary", () => {
  it("counts booked and free slots and books the next free one", async () => {
    const onBook = vi.fn();
    render(
      <DaySummary
        slots={[slot(9, "BOOKED"), slot(10, "FREE"), slot(11, "FREE")]}
        onBook={onBook}
      />,
    );
    expect(document.body).toHaveTextContent("1 booked");
    expect(document.body).toHaveTextContent("2 free");
    await userEvent.click(screen.getByRole("button", { name: "Book it" }));
    expect(onBook).toHaveBeenCalledWith("2026-10-19T10:00:00+05:30");
    expect(screen.getByText("Select a booked slot to see the details.")).toBeInTheDocument();
  });

  it("says so when nothing is free", () => {
    render(<DaySummary slots={[slot(9, "BOOKED")]} onBook={vi.fn()} />);
    expect(screen.getByText(/Nothing is free on this day/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Book it" })).not.toBeInTheDocument();
  });
});
