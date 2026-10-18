import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "./App";
import { titleFor } from "./components/PageChrome";
import { installFakeApi } from "./test/fakeApi";
import { clockInfo, doctor, renderPage } from "./test/utils";

const routes = () => ({
  "GET /auth/status": { body: { required: false } },
  "GET /clock": { body: clockInfo() },
  "GET /doctors": { body: [doctor()] },
  "GET /needs-attention": { body: { items: [], total: 0, limit: 1, offset: 0 } },
  "GET /queue": { body: [] },
  "GET /patients": { body: { items: [], total: 0, limit: 10, offset: 0 } },
});

describe("page chrome", () => {
  it("names the tab after the page", () => {
    expect(titleFor("/queue")).toBe("Queue · Clinic Scheduler");
    expect(titleFor("/patients/7")).toBe("Patients · Clinic Scheduler");
    expect(titleFor("/nowhere")).toBe("Clinic Scheduler");
  });

  it("has a skip link that points at the focusable main region", async () => {
    installFakeApi(routes());
    renderPage(<App />, "/queue");
    const skip = await screen.findByRole("link", { name: "Skip to the page" });
    expect(skip).toHaveAttribute("href", "#main");
    const main = await screen.findByRole("main");
    expect(main).toHaveAttribute("id", "main");
    expect(main).toHaveAttribute("tabindex", "-1");
  });

  it("moves focus to the page and sets the title after a navigation", async () => {
    installFakeApi(routes());
    const user = userEvent.setup();
    renderPage(<App />, "/queue");
    await user.click(await screen.findByRole("link", { name: "Patients" }));
    expect(document.title).toBe("Patients · Clinic Scheduler");
    expect(screen.getByRole("main")).toHaveFocus();
  });

  it("says so when the browser goes offline, and stops when it is back", async () => {
    installFakeApi(routes());
    renderPage(<App />, "/queue");
    await screen.findByRole("main");
    expect(screen.queryByText(/You are offline/)).not.toBeInTheDocument();

    const setOnline = (value: boolean) =>
      Object.defineProperty(window.navigator, "onLine", { value, configurable: true });
    act(() => {
      setOnline(false);
      window.dispatchEvent(new Event("offline"));
    });
    expect(await screen.findByText(/You are offline/)).toBeInTheDocument();
    act(() => {
      setOnline(true);
      window.dispatchEvent(new Event("online"));
    });
    expect(screen.queryByText(/You are offline/)).not.toBeInTheDocument();
  });
});
