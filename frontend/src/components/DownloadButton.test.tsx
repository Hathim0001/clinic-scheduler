import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetSessionCache, setSession } from "../lib/authStore";
import { apiError, installFakeApi } from "../test/fakeApi";
import { renderPage } from "../test/utils";
import { DownloadButton } from "./DownloadButton";

beforeEach(() => {
  window.sessionStorage.clear();
  resetSessionCache();
  URL.createObjectURL = vi.fn(() => "blob:test");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  setSession(null);
  vi.restoreAllMocks();
});

describe("a file download", () => {
  it("fetches the file with the sign-in token and offers it to the browser", async () => {
    setSession({ token: "abc.def", name: "Meera", role: "ADMIN" });
    const api = installFakeApi({ "GET /reports/summary.csv": { body: {} } });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const user = userEvent.setup();
    renderPage(
      <DownloadButton
        path="/reports/summary.csv"
        query={{ from: "2026-11-01", to: "2026-11-02" }}
        fallbackName="report.csv"
        label="Download CSV"
      />,
    );
    await user.click(screen.getByRole("button", { name: "Download CSV" }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    const call = api.last("GET", "/reports/summary.csv");
    expect(call?.headers.get("Authorization")).toBe("Bearer abc.def");
    expect(call?.query).toEqual({ from: "2026-11-01", to: "2026-11-02" });
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test");
  });

  it("shows the server's reason when the download is refused", async () => {
    installFakeApi({ "GET /patients/7/export": apiError(403, "FORBIDDEN", "Only an admin.") });
    const user = userEvent.setup();
    renderPage(
      <DownloadButton path="/patients/7/export" fallbackName="p.json" label="Download records" />,
    );
    await user.click(screen.getByRole("button", { name: "Download records" }));
    expect(await screen.findByText("Only an administrator can do this.")).toBeInTheDocument();
  });
});
