import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { ClockProvider } from "../lib/clock";
import { loadTestClock } from "../lib/clockStore";
import { request } from "../api/client";
import { apiError, installFakeApi } from "../test/fakeApi";
import { clockInfo, renderPage } from "../test/utils";
import { ClockBar } from "./ClockBar";
import { WakeBanner } from "./WakeBanner";

describe("the clock bar", () => {
  it("shows the server time and the controls when the server allows a test clock", async () => {
    installFakeApi({ "GET /clock": { body: clockInfo() } });
    renderPage(<ClockBar />);
    expect(await screen.findByText(/Server time 2 Nov 2026, 08:00 IST \(real clock\)/)).toBeInTheDocument();
    expect(screen.getByLabelText("Test clock (India time)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Seed day 09:30" })).toBeInTheDocument();
    expect(screen.queryByText(/TEST CLOCK ACTIVE/)).not.toBeInTheDocument();
  });

  it("hides the controls when the server does not allow a test clock", async () => {
    installFakeApi({ "GET /clock": { body: clockInfo({ test_clock_enabled: false }) } });
    renderPage(<ClockBar />);
    await screen.findByText(/Server time/);
    expect(screen.queryByLabelText("Test clock (India time)")).not.toBeInTheDocument();
  });

  it("sets a test clock from India time, shows the amber badge, remembers it and sends it", async () => {
    const api = installFakeApi({ "GET /clock": { body: clockInfo() }, "GET /doctors": { body: [] } });
    const user = userEvent.setup();
    renderPage(<ClockBar />);

    const input = await screen.findByLabelText("Test clock (India time)");
    await user.type(input, "2026-11-02T10:05");
    await user.click(screen.getByRole("button", { name: "Set clock" }));

    expect(await screen.findByText("TEST CLOCK ACTIVE: 2 Nov 2026, 10:05 IST")).toBeInTheDocument();
    expect(loadTestClock()).toBe("2026-11-02T10:05:00+05:30");
    await waitFor(() =>
      expect(api.last("GET", "/clock")?.headers.get("x-test-clock")).toBe("2026-11-02T10:05:00+05:30"),
    );
    await request("GET", "/doctors");
    expect(api.last("GET", "/doctors")?.headers.get("x-test-clock")).toBe("2026-11-02T10:05:00+05:30");
  });

  it("applies the seed-day preset at 09:30 India time", async () => {
    const api = installFakeApi({ "GET /clock": { body: clockInfo() } });
    const user = userEvent.setup();
    renderPage(<ClockBar />);
    await user.click(await screen.findByRole("button", { name: "Seed day 09:30" }));
    expect(await screen.findByText("TEST CLOCK ACTIVE: 19 Oct 2026, 09:30 IST")).toBeInTheDocument();
    await waitFor(() =>
      expect(api.last("GET", "/clock")?.headers.get("x-test-clock")).toBe("2026-10-19T09:30:00+05:30"),
    );
  });

  it("goes back to the real time", async () => {
    const api = installFakeApi({ "GET /clock": { body: clockInfo() } });
    const user = userEvent.setup();
    renderPage(<ClockBar />);
    await user.click(await screen.findByRole("button", { name: "Seed day 09:30" }));
    await user.click(await screen.findByRole("button", { name: "Use the real time" }));

    await waitFor(() => expect(screen.queryByText(/TEST CLOCK ACTIVE/)).not.toBeInTheDocument());
    expect(loadTestClock()).toBeNull();
    await waitFor(() => expect(api.last("GET", "/clock")?.headers.has("x-test-clock")).toBe(false));
  });

  it("restores a clock chosen before a reload, so the first request already carries it", async () => {
    window.localStorage.setItem("clinic.testClock", "2026-11-02T09:00:00+05:30");
    const api = installFakeApi({ "GET /clock": { body: clockInfo({ source: "HEADER" }) } });
    renderPage(<ClockBar />);
    expect(await screen.findByText("TEST CLOCK ACTIVE: 2 Nov 2026, 09:00 IST")).toBeInTheDocument();
    expect(api.calls[0]?.headers.get("x-test-clock")).toBe("2026-11-02T09:00:00+05:30");
  });

  it("can always be cleared, even when the server refuses the clock that was stored", async () => {
    window.localStorage.setItem("clinic.testClock", "2026-11-02T09:00:00+05:30");
    installFakeApi({
      "GET /clock": apiError(400, "INVALID_TEST_CLOCK", "The test clock is disabled on this server."),
    });
    const user = userEvent.setup();
    renderPage(<ClockBar />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The test clock is disabled on this server.");
    await user.click(screen.getByRole("button", { name: "Use the real time" }));
    expect(loadTestClock()).toBeNull();
  });
});

describe("the wake-up banner", () => {
  const withProviders = () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={client}>
        <ClockProvider>
          <MemoryRouter>
            <WakeBanner />
          </MemoryRouter>
        </ClockProvider>
      </QueryClientProvider>,
    );
  };

  it("says the server is waking up when it has not answered after three seconds", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    withProviders();
    expect(screen.queryByText(/Waking the server/)).not.toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(screen.getByText(/Waking the server, this can take up to a minute/)).toBeInTheDocument();
  });

  it("stays quiet when the server answers quickly", async () => {
    vi.useFakeTimers();
    installFakeApi({});
    withProviders();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(screen.queryByText(/Waking the server/)).not.toBeInTheDocument();
  });
});
