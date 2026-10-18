import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { PatientPicker } from "../components/PatientPicker";
import { PrivacyPanel } from "../components/PrivacyPanel";
import { installFakeApi } from "../test/fakeApi";
import { appointment, clockInfo, doctor, patient, renderPage } from "../test/utils";
import Book from "./Book";
import Calls from "./Calls";
import Reports from "./Reports";

const slots = {
  doctor_id: 1,
  date: "2026-11-02",
  slot_length_min: 30,
  source: "WEEKLY",
  windows: [{ start: "09:00", end: "13:00" }],
  slots: [],
  unavailable_reason: "FULLY_BOOKED",
  duration_min: 30,
};

describe("a patient who already has a booking that day", () => {
  it("is mentioned before a second visit is booked", async () => {
    installFakeApi({
      "GET /clock": { body: clockInfo() },
      "GET /doctors": { body: [doctor()] },
      "GET /patients/7": { body: patient() },
      "GET /patients/7/appointments": {
        body: { items: [appointment({ id: 50 })], total: 1, limit: 100, offset: 0 },
      },
      "GET /doctors/1/slots": { body: slots },
      "GET /alternatives": { body: [] },
    });
    renderPage(<Book />, "/book?patient=7&doctor=1&date=2026-11-02");
    expect(await screen.findByText(/already has an appointment on this day/)).toBeInTheDocument();
  });

  it("is not mentioned for a cancelled appointment or another day", async () => {
    installFakeApi({
      "GET /clock": { body: clockInfo() },
      "GET /doctors": { body: [doctor()] },
      "GET /patients/7": { body: patient() },
      "GET /patients/7/appointments": {
        body: {
          items: [
            appointment({ id: 50, status: "CANCELLED" }),
            appointment({ id: 51, start_at_ist: "2026-11-03T10:00:00+05:30" }),
          ],
          total: 2,
          limit: 100,
          offset: 0,
        },
      },
      "GET /doctors/1/slots": { body: slots },
      "GET /alternatives": { body: [] },
    });
    renderPage(<Book />, "/book?patient=7&doctor=1&date=2026-11-02");
    await screen.findByText(/Nothing else is free|Nearest available/);
    expect(screen.queryByText(/already has an appointment on this day/)).not.toBeInTheDocument();
  });
});

describe("calls for tomorrow", () => {
  const routes = (extra = {}) => ({
    "GET /clock": { body: clockInfo() },
    "GET /queue": {
      body: [
        appointment({ id: 61, patient_name: "Meera Das" }),
        appointment({ id: 62, patient_name: "Ravi Kumar", confirmed_by_phone_at_utc: "x" }),
        appointment({ id: 63, patient_name: "Gone Away", status: "CANCELLED" }),
      ],
    },
    ...extra,
  });

  it("lists booked appointments with a Called button until one is recorded", async () => {
    const api = installFakeApi(
      routes({ "POST /appointments/61/confirmed-by-phone": { body: appointment({ id: 61 }) } }),
    );
    const user = userEvent.setup();
    renderPage(<Calls />);
    expect(await screen.findByText("Meera Das")).toBeInTheDocument();
    expect(screen.queryByText("Gone Away")).not.toBeInTheDocument();
    expect(screen.getByText("1 of 2 confirmed by phone.")).toBeInTheDocument();
    expect(api.last("GET", "/queue")?.query.date).toBe("2026-11-03"); // tomorrow
    await user.click(screen.getByRole("button", { name: "Mark Meera Das as called" }));
    expect(api.count("POST", "/appointments/61/confirmed-by-phone")).toBe(1);
    expect(screen.queryByRole("button", { name: "Mark Ravi Kumar as called" })).toBeNull();
  });

  it("says when there is nothing to confirm", async () => {
    installFakeApi({ "GET /clock": { body: clockInfo() }, "GET /queue": { body: [] } });
    renderPage(<Calls />);
    expect(await screen.findByText("Nothing to confirm.")).toBeInTheDocument();
  });
});

describe("a child's consent", () => {
  it("asks for a guardian and sends it as a guardian's", async () => {
    const api = installFakeApi({
      "GET /clock": { body: clockInfo() },
      "POST /patients/7/consent": { body: patient() },
    });
    const user = userEvent.setup();
    renderPage(<PrivacyPanel patient={patient({ date_of_birth: "2015-06-01" })} />);
    expect(await screen.findByText(/under 18: a parent or guardian must accept/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Record guardian's consent" }));
    expect(api.last("POST", "/patients/7/consent")?.body).toEqual({ consent_by: "GUARDIAN" });
  });

  it("shows who accepted it once recorded", async () => {
    installFakeApi({ "GET /clock": { body: clockInfo() } });
    renderPage(
      <PrivacyPanel
        patient={patient({
          date_of_birth: "2015-06-01",
          consent_at_utc: "2026-11-02T02:30:00Z",
          consent_by: "GUARDIAN",
        })}
      />,
    );
    expect(await screen.findByText(/by a parent or guardian on/)).toBeInTheDocument();
  });

  it("changes the checkbox wording for a child on the registration form", async () => {
    installFakeApi({
      "GET /clock": { body: clockInfo() },
      "GET /patients": { body: { items: [], total: 0, limit: 10, offset: 0 } },
    });
    const user = userEvent.setup();
    renderPage(<PatientPicker onSelect={() => undefined} />);
    await user.type(screen.getByLabelText("Find a patient by phone or name"), "Nobody{Enter}");
    await user.click(await screen.findByRole("button", { name: "New patient" }));
    const form = await screen.findByRole("form", { name: "New patient" });
    await user.type(within(form).getByLabelText("Date of birth"), "2015-06-01");
    expect(within(form).getByLabelText(/parent or guardian has accepted/)).toBeInTheDocument();
  });
});

describe("the report as a CSV", () => {
  it("has a download button for the chosen range", async () => {
    installFakeApi({
      "GET /clock": { body: clockInfo() },
      "GET /reports/summary": {
        body: { start: "2026-10-27", end: "2026-11-02", doctors: [], total: null },
      },
    });
    renderPage(<Reports />);
    expect(await screen.findByRole("button", { name: "Download as CSV" })).toBeInTheDocument();
  });
});
