import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { apiError, installFakeApi } from "../test/fakeApi";
import { patient, renderPage } from "../test/utils";
import { PrivacyPanel } from "./PrivacyPanel";

describe("consent and erasure", () => {
  it("records consent when asked", async () => {
    const api = installFakeApi({
      "POST /patients/7/consent": { body: patient({ consent_at_utc: "2026-11-02T02:30:00Z" }) },
    });
    const user = userEvent.setup();
    renderPage(<PrivacyPanel patient={patient()} />);
    expect(screen.getByText(/has not been recorded/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Record consent" }));
    expect(api.count("POST", "/patients/7/consent")).toBe(1);
  });

  it("shows when consent was given", () => {
    installFakeApi({});
    renderPage(<PrivacyPanel patient={patient({ consent_at_utc: "2026-11-02T02:30:00Z" })} />);
    expect(screen.getByText(/Accepted the privacy notice on/)).toBeInTheDocument();
  });

  it("asks twice before erasing and says what stays", async () => {
    const api = installFakeApi({
      "POST /patients/7/erase": { body: patient({ erased: true, name: "Erased patient" }) },
    });
    const user = userEvent.setup();
    renderPage(<PrivacyPanel patient={patient()} />);
    await user.click(screen.getByRole("button", { name: /Erase this patient/ }));
    expect(api.count("POST", "/patients/7/erase")).toBe(0);
    expect(screen.getByText(/cannot be undone/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Erase permanently" }));
    expect(api.count("POST", "/patients/7/erase")).toBe(1);
  });

  it("can be cancelled before anything is sent", async () => {
    const api = installFakeApi({});
    const user = userEvent.setup();
    renderPage(<PrivacyPanel patient={patient()} />);
    await user.click(screen.getByRole("button", { name: /Erase this patient/ }));
    await user.click(screen.getByRole("button", { name: "Keep the data" }));
    expect(screen.queryByText(/cannot be undone/)).not.toBeInTheDocument();
    expect(api.count("POST", "/patients/7/erase")).toBe(0);
  });

  it("explains why an erasure was refused", async () => {
    installFakeApi({
      "POST /patients/7/erase": apiError(409, "PATIENT_HAS_UPCOMING", "upcoming", {}),
    });
    const user = userEvent.setup();
    renderPage(<PrivacyPanel patient={patient()} />);
    await user.click(screen.getByRole("button", { name: /Erase this patient/ }));
    await user.click(screen.getByRole("button", { name: "Erase permanently" }));
    expect(await screen.findByText(/still has an upcoming appointment/)).toBeInTheDocument();
  });

  it("shows only a notice for a patient who was already erased", () => {
    installFakeApi({});
    renderPage(<PrivacyPanel patient={patient({ erased: true })} />);
    expect(screen.getByText(/erased on request/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
