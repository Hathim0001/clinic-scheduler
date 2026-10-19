import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { SlotsResponse } from "../api/types";
import { apiError, installFakeApi } from "../test/fakeApi";
import { appointment, clockInfo, doctor, flaggedDeposit, patient, renderPage } from "../test/utils";
import Book from "./Book";

const slot = (hour: string, startUtc: string, endUtc: string, endHour: string) => ({
  start_at_utc: startUtc,
  start_at_ist: `2026-11-02T${hour}:00+05:30`,
  end_at_utc: endUtc,
  end_at_ist: `2026-11-02T${endHour}:00+05:30`,
});

const slots: SlotsResponse = {
  doctor_id: 1,
  date: "2026-11-02",
  slot_length_min: 30,
  source: "WEEKLY",
  windows: [{ start: "09:00", end: "13:00" }],
  slots: [
    slot("10:00", "2026-11-02T04:30:00Z", "2026-11-02T05:00:00Z", "10:30"),
    slot("10:30", "2026-11-02T05:00:00Z", "2026-11-02T05:30:00Z", "11:00"),
  ],
  unavailable_reason: null,
  duration_min: 30,
};

const routes = (extra = {}) => ({
  "GET /clock": { body: clockInfo() },
  "GET /doctors": { body: [doctor()] },
  "GET /patients/7": { body: patient() },
  "GET /doctors/1/slots": { body: slots },
  ...extra,
});

const link = "/book?patient=7&doctor=1&date=2026-11-02";

describe("booking an appointment", () => {
  it("offers only the times the server lists, in IST, and books the chosen one", async () => {
    const api = installFakeApi(
      routes({ "POST /appointments": { status: 201, body: appointment() } }),
    );
    const user = userEvent.setup();
    renderPage(<Book />, link);

    await user.click(await screen.findByRole("button", { name: "10:00–10:30" }));
    await user.type(screen.getByLabelText("Reason"), "Fever, 3 days");
    await user.click(screen.getByRole("button", { name: "Book the appointment" }));

    await waitFor(() => expect(api.count("POST", "/appointments")).toBe(1));
    expect(api.last("POST", "/appointments")?.body).toEqual({
      doctor_id: 1,
      patient_id: 7,
      start_at: "2026-11-02T10:00:00+05:30",
      reason: "Fever, 3 days",
      deposit_confirmed: false,
      slots: 1,
    });
    expect(await screen.findByText(/Booked: Kavita Nair with Dr. Rao/)).toBeInTheDocument();
  });

  it("asks for the slots of the chosen patient, so times that patient cannot take are left out", async () => {
    const api = installFakeApi(routes());
    renderPage(<Book />, link);
    await screen.findByRole("button", { name: "10:00–10:30" });
    expect(api.last("GET", "/doctors/1/slots")?.query).toMatchObject({
      date: "2026-11-02",
      patient_id: "7",
    });
  });

  it("keeps the button off until a slot and a reason are chosen", async () => {
    installFakeApi(routes());
    const user = userEvent.setup();
    renderPage(<Book />, link);
    const slotButton = await screen.findByRole("button", { name: "10:00–10:30" });
    const submit = screen.getByRole("button", { name: "Book the appointment" });
    expect(submit).toBeDisabled();
    await user.click(slotButton);
    expect(submit).toBeDisabled(); // still no reason
    await user.type(screen.getByLabelText("Reason"), "Check-up");
    expect(submit).toBeEnabled();
  });

  it("shows the deposit box only for a flagged patient, with the reasons, and requires it", async () => {
    const api = installFakeApi(
      routes({
        "GET /patients/7": { body: patient({ deposit: flaggedDeposit }) },
        "POST /appointments": {
          status: 201,
          body: appointment({ deposit_required_at_booking: true, deposit_confirmed: true }),
        },
      }),
    );
    const user = userEvent.setup();
    renderPage(<Book />, link);

    expect(
      await screen.findByText(/Deposit required until 27 Nov 2026, 15:10 IST/),
    ).toBeInTheDocument();
    expect(screen.getByText(/No-show on 29 Oct 2026, 10:00 IST/)).toBeInTheDocument();
    expect(screen.getByText(/Late cancellation on 28 Oct 2026, 15:10 IST/)).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "10:00–10:30" }));
    await user.type(screen.getByLabelText("Reason"), "Follow-up");
    const submit = screen.getByRole("button", { name: "Book the appointment" });
    expect(submit).toBeDisabled(); // the deposit has not been acknowledged yet

    await user.click(screen.getByLabelText(/acknowledged the deposit/));
    expect(submit).toBeEnabled();
    await user.click(submit);

    await waitFor(() =>
      expect(api.last("POST", "/appointments")?.body).toMatchObject({ deposit_confirmed: true }),
    );
  });

  it("does not show a deposit box for a patient who is not flagged", async () => {
    installFakeApi(routes());
    renderPage(<Book />, link);
    await screen.findByRole("button", { name: "10:00–10:30" });
    expect(screen.queryByLabelText(/acknowledged the deposit/)).not.toBeInTheDocument();
  });

  it("says so, and refreshes the slots, when someone else took the slot", async () => {
    const api = installFakeApi(
      routes({
        "POST /appointments": apiError(409, "SLOT_TAKEN", "taken", { same_patient: false }),
      }),
    );
    const user = userEvent.setup();
    renderPage(<Book />, link);
    await user.click(await screen.findByRole("button", { name: "10:00–10:30" }));
    await user.type(screen.getByLabelText("Reason"), "Check-up");
    const before = api.count("GET", "/doctors/1/slots");

    await user.click(screen.getByRole("button", { name: "Book the appointment" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Someone just booked this slot. The list has been refreshed.",
    );
    await waitFor(() => expect(api.count("GET", "/doctors/1/slots")).toBeGreaterThan(before));
  });

  it("names the doctor when the day is full", async () => {
    installFakeApi(routes({ "POST /appointments": apiError(409, "DAILY_CAP_REACHED", "cap") }));
    const user = userEvent.setup();
    renderPage(<Book />, link);
    await user.click(await screen.findByRole("button", { name: "10:00–10:30" }));
    await user.type(screen.getByLabelText("Reason"), "Check-up");
    await user.click(screen.getByRole("button", { name: "Book the appointment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Dr. Rao is fully booked on that day.",
    );
  });

  it("explains an empty day with the server's reason instead of guessing", async () => {
    installFakeApi(
      routes({
        "GET /doctors/1/slots": {
          body: { ...slots, slots: [], unavailable_reason: "DAILY_CAP_REACHED" },
        },
      }),
    );
    renderPage(<Book />, link);
    expect(
      await screen.findByText(
        /The doctor has reached the daily limit of appointments for this date/,
      ),
    ).toBeInTheDocument();
  });

  it("moves an existing appointment in reschedule mode, for the same patient", async () => {
    const original = appointment({ id: 41 });
    const api = installFakeApi(
      routes({
        "GET /appointments/41": { body: original },
        "POST /appointments/41/reschedule": {
          body: {
            old: { ...original, status: "CANCELLED", allowed_actions: [] },
            new: appointment({ id: 42 }),
          },
        },
      }),
    );
    const user = userEvent.setup();
    renderPage(<Book />, "/book?reschedule=41");

    expect(
      await screen.findByText(/Moving Kavita Nair's appointment from 2 Nov 2026, 10:00 IST/),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Reason")).not.toBeInTheDocument(); // the reason is carried over
    await user.click(await screen.findByRole("button", { name: "10:30–11:00" }));
    await user.click(screen.getByRole("button", { name: "Move the appointment" }));

    await waitFor(() => expect(api.count("POST", "/appointments/41/reschedule")).toBe(1));
    expect(api.last("POST", "/appointments/41/reschedule")?.body).toEqual({
      start_at: "2026-11-02T10:30:00+05:30",
      doctor_id: 1,
      by: "PATIENT",
    });
  });

  it("starts with the patient of the last booking, and says so", async () => {
    installFakeApi(routes());
    window.sessionStorage.setItem("clinic.lastPatientId", "7");
    renderPage(<Book />, "/book?doctor=1&date=2026-11-02");

    expect(await screen.findByText(/same patient as the last booking/)).toBeInTheDocument();
    expect(screen.getByText("Kavita Nair", { exact: false })).toBeInTheDocument();
  });

  it("does not prefill a patient when a link names one or nothing was booked", async () => {
    installFakeApi(routes());
    renderPage(<Book />, link);
    await screen.findByRole("button", { name: "10:00–10:30" });
    expect(screen.queryByText(/same patient as the last booking/)).not.toBeInTheDocument();
  });

  it("remembers the patient after a successful booking", async () => {
    installFakeApi(routes({ "POST /appointments": { status: 201, body: appointment() } }));
    const user = userEvent.setup();
    renderPage(<Book />, link);
    await user.click(await screen.findByRole("button", { name: "10:00–10:30" }));
    await user.type(screen.getByLabelText("Reason"), "Fever");
    await user.click(screen.getByRole("button", { name: "Book the appointment" }));

    await waitFor(() => expect(window.sessionStorage.getItem("clinic.lastPatientId")).toBe("7"));
  });
});
