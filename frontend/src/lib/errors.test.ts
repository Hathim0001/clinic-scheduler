import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { describeError, whyDisabled } from "./errors";

const error = (code: string, details: Record<string, unknown> = {}, message = "server words") =>
  new ApiError(409, code, message, details, "req-1");

describe("error messages", () => {
  it("tells a double click from a lost race", () => {
    expect(describeError(error("SLOT_TAKEN", { same_patient: true })).message).toBe(
      "This patient is already booked in this slot.",
    );
    expect(describeError(error("SLOT_TAKEN", { same_patient: false })).message).toBe(
      "Someone just booked this slot. The list has been refreshed.",
    );
  });

  it("names the doctor where the plan says to", () => {
    const context = { doctorName: "Dr. Rao" };
    expect(describeError(error("DAILY_CAP_REACHED"), context).message).toBe(
      "Dr. Rao is fully booked on that day.",
    );
    expect(describeError(error("OUTSIDE_AVAILABILITY"), context).message).toBe(
      "Dr. Rao is not available at that time. Pick one of the listed slots.",
    );
    expect(describeError(error("OFF_GRID"), context).message).toContain("Dr. Rao");
  });

  it.each([
    ["PATIENT_OVERLAP", "This patient already has an appointment at that time."],
    ["BOOKING_IN_PAST", "That time has passed."],
    ["TOO_EARLY_TO_MARK", "An appointment can only be marked once it has started."],
  ])("%s", (code, message) => {
    expect(describeError(error(code)).message).toBe(message);
  });

  it("names the clinic's own booking horizon when the server sends it", () => {
    expect(describeError(error("BOOKING_TOO_FAR", { horizon_days: 45 })).message).toBe(
      "Bookings open up to 45 days ahead.",
    );
    expect(describeError(error("BOOKING_TOO_FAR")).message).toBe(
      "That date is further ahead than the clinic takes bookings.",
    );
  });

  it("keeps the request id so a failure can be found in the server logs", () => {
    expect(describeError(error("SOMETHING_NEW")).requestId).toBe("req-1");
  });

  it("falls back to the words of the server for codes it does not know", () => {
    const friendly = describeError(
      error("INVALID_TRANSITION", {}, "This appointment is already cancelled."),
    );
    expect(friendly.message).toBe("This appointment is already cancelled.");
  });

  it("offers a retry only when the server was busy or unreachable", () => {
    expect(describeError(error("SERVICE_UNAVAILABLE")).retryable).toBe(true);
    expect(describeError(new ApiError(0, "NETWORK_ERROR", "x")).retryable).toBe(true);
    expect(describeError(error("SLOT_TAKEN")).retryable).toBe(false);
  });

  it("lists the invalid fields of a form without raw JSON", () => {
    const friendly = describeError(
      new ApiError(422, "VALIDATION_ERROR", "bad", {
        fields: [
          { loc: ["body", "date_of_birth"], msg: "must be a real calendar date", type: "x" },
        ],
      }),
    );
    expect(friendly.lines).toEqual(["date_of_birth: must be a real calendar date"]);
  });

  it("does not leak details for an error that is not from the API", () => {
    const friendly = describeError(new TypeError("undefined is not a function"));
    expect(friendly.message).toBe("Something unexpected went wrong in the page.");
    expect(friendly.message).not.toContain("undefined");
  });
});

describe("why a button is switched off", () => {
  it("names the status of a finished appointment", () => {
    expect(whyDisabled("cancel", "CANCELLED")).toContain("cancelled");
    expect(whyDisabled("complete", "NO_SHOW")).toContain("no-show");
    expect(whyDisabled("reschedule", "COMPLETED")).toContain("completed");
  });

  it("explains the clock for a booked appointment", () => {
    expect(whyDisabled("no-show", "BOOKED")).toBe("Cannot mark this appointment before it starts.");
    expect(whyDisabled("cancel", "BOOKED")).toContain("already started");
  });
});
