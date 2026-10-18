import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { installFakeApi } from "../test/fakeApi";
import { renderPage } from "../test/utils";
import Messages from "./Messages";

const message = (over = {}) => ({
  id: 1,
  patient_id: 7,
  appointment_id: 41,
  kind: "APPOINTMENT_BOOKED",
  to_phone: "+919000000001",
  body: "Your appointment with Dr. Rao is booked.",
  status: "PENDING",
  attempts: 0,
  last_error: null,
  created_at_utc: "2026-11-02T02:30:00Z",
  sent_at_utc: null,
  sent_via: null,
  ...over,
});

const page = (items: unknown[], total = items.length) => ({
  body: { items, total, limit: 20, offset: 0 },
});

describe("messages to patients", () => {
  it("lists them and marks one as sent by hand", async () => {
    const api = installFakeApi({
      "GET /notifications": page([message()]),
      "POST /notifications/1/sent": { body: message({ status: "SENT", sent_via: "MANUAL" }) },
    });
    const user = userEvent.setup();
    renderPage(<Messages />);
    expect(await screen.findByText(/Dr\. Rao is booked/)).toBeInTheDocument();
    expect(screen.getByText("+919000000001")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mark as sent" }));
    expect(api.count("POST", "/notifications/1/sent")).toBe(1);
  });

  it("tells reception to phone a patient who has not consented", async () => {
    installFakeApi({
      "GET /notifications": page([
        message({
          status: "SKIPPED",
          last_error: "No consent recorded: tell the patient by phone.",
        }),
      ]),
    });
    renderPage(<Messages />);
    expect(await screen.findByText(/No consent recorded/)).toBeInTheDocument();
  });

  it("shows how a sent message went out and offers no action on it", async () => {
    installFakeApi({
      "GET /notifications": page([
        message({ status: "SENT", sent_via: "GATEWAY", sent_at_utc: "2026-11-02T03:00:00Z" }),
      ]),
    });
    renderPage(<Messages />);
    expect(await screen.findByText(/by the gateway/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark as sent" })).not.toBeInTheDocument();
  });

  it("filters by status and says when there is nothing", async () => {
    const api = installFakeApi({ "GET /notifications": page([]) });
    const user = userEvent.setup();
    renderPage(<Messages />);
    expect(await screen.findByText("No messages here.")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Show"), "FAILED");
    await screen.findByText("No messages here.");
    expect(api.last("GET", "/notifications")?.query.status).toBe("FAILED");
  });
});
