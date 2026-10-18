import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { apiError, installFakeApi, type Call } from "../test/fakeApi";
import { appointment, clockInfo, doctor, renderPage } from "../test/utils";
import Admin from "./Admin";

const affected = [
  {
    id: 41,
    patient_name: "Kavita Nair",
    patient_phone: "+919000000001",
    start_at_ist: "2026-11-02T10:00:00+05:30",
  },
  {
    id: 42,
    patient_name: "Rahul Verma",
    patient_phone: "+919000000002",
    start_at_ist: "2026-11-09T10:30:00+05:30",
  },
];

const conflictReply = apiError(
  409,
  "AVAILABILITY_CONFLICTS",
  "2 future appointments would fall outside Dr. Rao's availability.",
  { doctor_id: 1, date: null, appointments: affected },
);

const weekly = { windows: [{ weekday: 0, start: "09:00", end: "13:00" }], needs_attention: [] };

const routes = (extra = {}) => ({
  "GET /clock": { body: clockInfo() },
  "GET /doctors": { body: [doctor()] },
  "GET /doctors/1/weekly-windows": { body: weekly },
  "GET /doctors/1/overrides": { body: [] },
  "GET /appointments": { body: { items: [], total: 0, limit: 100, offset: 0 } },
  ...extra,
});

/** A route that refuses until the request carries the acknowledgement. */
const refuseUntilAcknowledged = (success: unknown) => (call: Call) =>
  (call.body as { acknowledge_conflicts?: boolean }).acknowledge_conflicts === true
    ? { body: success }
    : conflictReply;

describe("doctors and availability", () => {
  it("shows the weekly hours and the doctor's details", async () => {
    installFakeApi(routes());
    renderPage(<Admin />, "/admin");
    expect(await screen.findByLabelText("Monday window from")).toHaveValue("09:00");
    expect(screen.getByLabelText("Monday window to")).toHaveValue("13:00");
    expect(screen.getAllByText("Not working")).toHaveLength(6); // Tuesday to Sunday
    expect(screen.getByLabelText("Appointments per day (limit)")).toHaveValue(6);
  });

  it("lists the affected patients and phones, and saves anyway only after confirmation", async () => {
    const api = installFakeApi(
      routes({
        "PUT /doctors/1/weekly-windows": refuseUntilAcknowledged({
          windows: [{ weekday: 0, start: "11:00", end: "13:00" }],
          needs_attention: [appointment({ id: 41, needs_attention: true })],
        }),
      }),
    );
    const user = userEvent.setup();
    renderPage(<Admin />, "/admin");

    const from = await screen.findByLabelText("Monday window from");
    await user.clear(from);
    await user.type(from, "11:00");
    await user.click(screen.getByRole("button", { name: "Save weekly hours" }));

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/Kavita Nair, \+919000000001, 2 Nov 2026, 10:00 IST/),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/Rahul Verma, \+919000000002/)).toBeInTheDocument();
    expect(api.count("PUT", "/doctors/1/weekly-windows")).toBe(1);
    expect(
      (api.last("PUT", "/doctors/1/weekly-windows")?.body as { acknowledge_conflicts: boolean })
        .acknowledge_conflicts,
    ).toBe(false);

    await user.click(within(dialog).getByRole("button", { name: "Save anyway" }));

    await waitFor(() => expect(api.count("PUT", "/doctors/1/weekly-windows")).toBe(2));
    expect(api.last("PUT", "/doctors/1/weekly-windows")?.body).toMatchObject({
      acknowledge_conflicts: true,
      windows: [{ weekday: 0, start: "11:00", end: "13:00" }],
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("changes nothing when the dialog is dismissed", async () => {
    const api = installFakeApi(routes({ "PUT /doctors/1/weekly-windows": conflictReply }));
    const user = userEvent.setup();
    renderPage(<Admin />, "/admin");

    await user.click(await screen.findByRole("button", { name: "Save weekly hours" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Go back" }),
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.count("PUT", "/doctors/1/weekly-windows")).toBe(1);
  });

  it("shows a refused window as words, with the field, not as JSON", async () => {
    installFakeApi(
      routes({
        "PUT /doctors/1/weekly-windows": apiError(
          422,
          "WINDOW_OFF_GRID",
          "The window 09:05-13:00 does not fall on the 30-minute slot grid.",
        ),
      }),
    );
    const user = userEvent.setup();
    renderPage(<Admin />, "/admin");
    await user.click(await screen.findByRole("button", { name: "Save weekly hours" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "does not fall on the 30-minute slot grid",
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("saves a leave day through the same conflict protocol", async () => {
    const api = installFakeApi(
      routes({
        "PUT /doctors/1/overrides/2026-11-02": refuseUntilAcknowledged({
          date: "2026-11-02",
          note: null,
          windows: [],
          needs_attention: [],
        }),
      }),
    );
    const user = userEvent.setup();
    renderPage(<Admin />, "/admin");

    await user.type(await screen.findByLabelText("Date"), "2026-11-02");
    await user.click(screen.getByRole("button", { name: "Save override" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Save anyway" }),
    );

    await waitFor(() => expect(api.count("PUT", "/doctors/1/overrides/2026-11-02")).toBe(2));
    expect(api.last("PUT", "/doctors/1/overrides/2026-11-02")?.body).toEqual({
      windows: [],
      note: null,
      acknowledge_conflicts: true,
    });
  });

  it("removes an override, and asks first when bookings would be affected", async () => {
    const api = installFakeApi(
      routes({
        "GET /doctors/1/overrides": {
          body: [
            {
              date: "2026-11-07",
              note: "Camp",
              windows: [{ start: "10:00", end: "12:00" }],
              needs_attention: [],
            },
          ],
        },
        "DELETE /doctors/1/overrides/2026-11-07": (call: Call) =>
          call.query.acknowledge_conflicts === "true" ? { status: 204 } : conflictReply,
      }),
    );
    const user = userEvent.setup();
    renderPage(<Admin />, "/admin");

    await user.click(await screen.findByRole("button", { name: "Remove 2026-11-07" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Save anyway" }),
    );

    await waitFor(() => expect(api.count("DELETE", "/doctors/1/overrides/2026-11-07")).toBe(2));
    expect(api.last("DELETE", "/doctors/1/overrides/2026-11-07")?.query.acknowledge_conflicts).toBe(
      "true",
    );
  });

  it("lists appointments that need attention with their actions", async () => {
    installFakeApi(
      routes({
        "GET /appointments": {
          body: {
            items: [appointment({ id: 50, patient_name: "Rahul Verma", needs_attention: true })],
            total: 1,
            limit: 100,
            offset: 0,
          },
        },
      }),
    );
    renderPage(<Admin />, "/admin");
    const card = await screen.findByRole("article", { name: "Appointment 50" });
    expect(card).toHaveTextContent("Needs attention");
    expect(within(card).getByRole("button", { name: "Reschedule" })).toBeEnabled();
  });

  it("explains why the slot length cannot change while bookings exist", async () => {
    installFakeApi(
      routes({
        "PATCH /doctors/1": apiError(
          409,
          "SLOT_LENGTH_LOCKED",
          "Dr. Rao has 3 future booked appointments made on the 30-minute grid.",
        ),
      }),
    );
    const user = userEvent.setup();
    renderPage(<Admin />, "/admin");
    await user.selectOptions(await screen.findByLabelText("Slot length"), "15");
    await user.click(screen.getByRole("button", { name: "Save details" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("3 future booked appointments");
  });
});
