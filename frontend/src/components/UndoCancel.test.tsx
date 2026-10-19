import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { apiError, installFakeApi } from "../test/fakeApi";
import { appointment, renderPage } from "../test/utils";
import { forgetCancel, rememberCancel } from "../lib/lastCancel";
import { UndoCancel } from "./UndoCancel";

const cancelled = appointment({
  id: 7,
  patient_name: "Neha Joshi",
  status: "CANCELLED",
  allowed_actions: ["undo-cancel"],
  etag: "v2",
});

afterEach(() => act(() => forgetCancel()));

describe("undoing a cancellation", () => {
  it("shows nothing until something was cancelled", () => {
    installFakeApi({});
    renderPage(<UndoCancel />);
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("does not offer undo when the server does not allow it", () => {
    installFakeApi({});
    renderPage(<UndoCancel />);
    act(() => rememberCancel({ ...cancelled, allowed_actions: [] }));
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("restores the appointment with its version and says so", async () => {
    const api = installFakeApi({
      "POST /appointments/7/undo-cancel": {
        body: { ...cancelled, status: "BOOKED", allowed_actions: ["cancel", "reschedule"] },
      },
    });
    const user = userEvent.setup();
    renderPage(<UndoCancel />);
    act(() => rememberCancel(cancelled));

    await user.click(await screen.findByRole("button", { name: "Undo" }));

    expect(await screen.findByText(/Restored Neha Joshi/)).toBeInTheDocument();
    expect(api.last("POST", "/appointments/7/undo-cancel")?.headers.get("If-Match")).toBe('"v2"');
  });

  it("explains why when the slot was taken meanwhile", async () => {
    installFakeApi({
      "POST /appointments/7/undo-cancel": apiError(
        409,
        "SLOT_TAKEN",
        "That time has just been taken by someone else.",
      ),
    });
    const user = userEvent.setup();
    renderPage(<UndoCancel />);
    act(() => rememberCancel(cancelled));

    await user.click(await screen.findByRole("button", { name: "Undo" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });

  it("goes away when dismissed", async () => {
    installFakeApi({});
    const user = userEvent.setup();
    renderPage(<UndoCancel />);
    act(() => rememberCancel(cancelled));

    await user.click(await screen.findByRole("button", { name: "Dismiss" }));

    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });
});
