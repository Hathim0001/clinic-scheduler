import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { apiError, installFakeApi } from "../test/fakeApi";
import { appointment, clockInfo, doctor, renderPage } from "../test/utils";
import Queue from "./Queue";

const started = appointment({
  id: 1,
  patient_name: "Meera Iyer",
  start_at_ist: "2026-11-02T09:00:00+05:30",
  end_at_ist: "2026-11-02T09:30:00+05:30",
  allowed_actions: ["complete", "no-show"],
});
const upcoming = appointment({
  id: 2,
  patient_name: "Neha Joshi",
  start_at_ist: "2026-11-02T11:00:00+05:30",
  end_at_ist: "2026-11-02T11:30:00+05:30",
  allowed_actions: ["cancel", "reschedule"],
});

const routes = (extra = {}) => ({
  "GET /clock": { body: clockInfo() },
  "GET /doctors": { body: [doctor()] },
  "GET /queue": { body: [started, upcoming] },
  ...extra,
});

const rowOf = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;

describe("today's queue", () => {
  it("lists the day in time order with the times in IST", async () => {
    installFakeApi(routes());
    renderPage(<Queue />, "/queue?date=2026-11-02");
    expect(await screen.findByText("Meera Iyer")).toBeInTheDocument();
    expect(within(rowOf("Meera Iyer")).getByText("09:00–09:30")).toBeInTheDocument();
    expect(within(rowOf("Neha Joshi")).getByText("11:00–11:30")).toBeInTheDocument();
    expect(screen.getByText(/Time \(IST\)/)).toBeInTheDocument();
  });

  it("enables each button from the actions the server allows, and says why the others are off", async () => {
    installFakeApi(routes());
    renderPage(<Queue />, "/queue?date=2026-11-02");
    await screen.findByText("Meera Iyer");

    const first = within(rowOf("Meera Iyer"));
    expect(first.getByRole("button", { name: "Complete" })).toBeEnabled();
    expect(first.getByRole("button", { name: "No-show" })).toBeEnabled();
    expect(first.getByRole("button", { name: "Reschedule" })).toBeDisabled();
    expect(first.getByRole("button", { name: "Reschedule" })).toHaveAttribute(
      "title",
      expect.stringContaining("already started"),
    );

    const second = within(rowOf("Neha Joshi"));
    expect(second.getByRole("button", { name: "Complete" })).toBeDisabled();
    expect(second.getByRole("button", { name: "No-show" })).toHaveAttribute(
      "title",
      "Cannot mark this appointment before it starts.",
    );
    expect(second.getByRole("button", { name: "Reschedule" })).toBeEnabled();
  });

  it("marks an appointment completed and refreshes the list", async () => {
    const api = installFakeApi(
      routes({
        "POST /appointments/1/complete": { body: { ...started, status: "COMPLETED", allowed_actions: [] } },
      }),
    );
    const user = userEvent.setup();
    renderPage(<Queue />, "/queue?date=2026-11-02");
    await screen.findByText("Meera Iyer");
    const before = api.count("GET", "/queue");

    await user.click(within(rowOf("Meera Iyer")).getByRole("button", { name: "Complete" }));

    await waitFor(() => expect(api.count("POST", "/appointments/1/complete")).toBe(1));
    await waitFor(() => expect(api.count("GET", "/queue")).toBeGreaterThan(before));
  });

  it("cancels as the clinic when asked to", async () => {
    const api = installFakeApi(
      routes({
        "POST /appointments/2/cancel": {
          body: {
            appointment: { ...upcoming, status: "CANCELLED", allowed_actions: [] },
            late: false,
            deposit: { required: false, required_until_utc: null, required_until_ist: null, reasons: [] },
          },
        },
      }),
    );
    const user = userEvent.setup();
    renderPage(<Queue />, "/queue?date=2026-11-02");
    await screen.findByText("Neha Joshi");

    const row = within(rowOf("Neha Joshi"));
    await user.click(row.getByRole("button", { name: "Cancel…" }));
    await user.click(row.getByLabelText(/The clinic/));
    await user.click(row.getByRole("button", { name: "Confirm cancellation" }));

    await waitFor(() => expect(api.last("POST", "/appointments/2/cancel")?.body).toEqual({ cancelled_by: "CLINIC" }));
  });

  it("shows the server's explanation, with the request id, when an action is refused", async () => {
    installFakeApi(
      routes({
        "POST /appointments/1/no-show": apiError(409, "TOO_EARLY_TO_MARK", "too early"),
      }),
    );
    const user = userEvent.setup();
    renderPage(<Queue />, "/queue?date=2026-11-02");
    await screen.findByText("Meera Iyer");

    await user.click(within(rowOf("Meera Iyer")).getByRole("button", { name: "No-show" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "An appointment can only be marked once it has started.",
    );
    expect(screen.getByText("req-test-1")).toBeInTheDocument();
  });

  it("suggests the seed day when a day is empty, and the preset sets the test clock", async () => {
    const api = installFakeApi(routes({ "GET /queue": { body: [] } }));
    const user = userEvent.setup();
    renderPage(<Queue />, "/queue?date=2026-11-02");

    expect(await screen.findByText(/No appointments on Mon 2 Nov 2026/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /set the test clock to that morning/ }));

    await waitFor(() =>
      expect(api.last("GET", "/queue")?.headers.get("x-test-clock")).toBe("2026-10-19T09:30:00+05:30"),
    );
  });

  it("asks the server for cancelled appointments only when told to", async () => {
    const api = installFakeApi(routes());
    const user = userEvent.setup();
    renderPage(<Queue />, "/queue?date=2026-11-02");
    await screen.findByText("Meera Iyer");
    expect(api.last("GET", "/queue")?.query.include_cancelled).toBe("false");

    await user.click(screen.getByLabelText("Show cancelled"));

    await waitFor(() => expect(api.last("GET", "/queue")?.query.include_cancelled).toBe("true"));
  });
});
