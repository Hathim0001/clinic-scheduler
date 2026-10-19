import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Component, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { request } from "../api/client";
import { getSession, resetSessionCache, setSession } from "../lib/authStore";
import { apiError, installFakeApi } from "../test/fakeApi";
import { renderPage } from "../test/utils";
import { AuthGate, ChangePasswordDialog, OpenAccessBanner } from "./AuthGate";
import { ErrorBoundary } from "./ErrorBoundary";

beforeEach(() => {
  window.sessionStorage.clear();
  resetSessionCache();
  setSession(null);
});

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
  resetSessionCache();
});

describe("the sign-in gate", () => {
  it("shows the app straight away when the server asks for no sign-in", async () => {
    installFakeApi({ "GET /auth/status": { body: { required: false } } });
    renderPage(
      <AuthGate>
        <p>the app</p>
      </AuthGate>,
    );
    expect(await screen.findByText("the app")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Staff sign-in" })).not.toBeInTheDocument();
  });

  it("shows the sign-in form when it is required and nobody is signed in", async () => {
    installFakeApi({ "GET /auth/status": { body: { required: true } } });
    renderPage(
      <AuthGate>
        <p>the app</p>
      </AuthGate>,
    );
    expect(await screen.findByRole("form", { name: "Staff sign-in" })).toBeInTheDocument();
    expect(screen.queryByText("the app")).not.toBeInTheDocument();
  });

  it("signs in, keeps the token for the tab, and sends it with every request", async () => {
    const api = installFakeApi({
      "GET /auth/status": { body: { required: true } },
      "POST /auth/login": {
        body: { token: "abc.def", name: "Meera", expires_at_epoch: 9_999_999_999 },
      },
      "GET /doctors": { body: [] },
    });
    const user = userEvent.setup();
    renderPage(
      <AuthGate>
        <p>the app</p>
      </AuthGate>,
    );
    const submit = await screen.findByRole("button", { name: "Sign in" });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText("Your name"), "Meera");
    await user.type(screen.getByLabelText("Staff password"), "clinic-secret-1");
    await user.click(submit);

    expect(await screen.findByText("the app")).toBeInTheDocument();
    expect(api.last("POST", "/auth/login")?.body).toEqual({
      name: "Meera",
      password: "clinic-secret-1",
    });
    expect(JSON.parse(window.sessionStorage.getItem("clinic.staffToken") ?? "null")).toEqual({
      token: "abc.def",
      name: "Meera",
      doctor_id: null,
    });
    await request("GET", "/doctors");
    expect(api.last("GET", "/doctors")?.headers.get("authorization")).toBe("Bearer abc.def");
  });

  it("says what to set when sign-in is required but was never set up", async () => {
    installFakeApi({
      "GET /auth/status": { body: { required: true, accounts: false, setup_needed: true } },
    });
    renderPage(
      <AuthGate>
        <p>the app</p>
      </AuthGate>,
    );
    expect(
      await screen.findByRole("heading", { name: "Sign-in is not set up yet" }),
    ).toBeInTheDocument();
    expect(screen.getByText("AUTH_SECRET")).toBeInTheDocument();
    expect(screen.queryByText("the app")).not.toBeInTheDocument();
  });

  it("offers the app and a warning when open access was chosen on purpose", async () => {
    installFakeApi({
      "GET /auth/status": { body: { required: false, accounts: false, open_access: true } },
    });
    renderPage(
      <AuthGate>
        <p>the app</p>
        <OpenAccessBanner />
      </AuthGate>,
    );
    expect(await screen.findByText("the app")).toBeInTheDocument();
    expect(screen.getByText("Demo mode.")).toBeInTheDocument();
    expect(screen.getByText(/Sign-in is switched off/)).toBeInTheDocument();
  });

  it("lets someone choose a new password with a reset code", async () => {
    const api = installFakeApi({
      "GET /auth/status": { body: { required: true, accounts: true } },
      "POST /auth/reset-password": { status: 204 },
    });
    const user = userEvent.setup();
    renderPage(
      <AuthGate>
        <p>the app</p>
      </AuthGate>,
    );
    await user.click(await screen.findByRole("button", { name: "Forgot your password?" }));
    await user.type(screen.getByLabelText("Username"), "meera");
    await user.type(screen.getByLabelText("Reset code"), "k7qx-92md");
    await user.type(
      screen.getByLabelText("New password (at least 8 characters)"),
      "a-brand-new-pass",
    );
    await user.type(screen.getByLabelText("New password again"), "a-brand-new-pass");
    await user.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByRole("heading", { name: "Password changed" })).toBeInTheDocument();
    expect(api.last("POST", "/auth/reset-password")?.body).toEqual({
      username: "meera",
      code: "K7QX-92MD",
      new_password: "a-brand-new-pass",
    });
    await user.click(screen.getByRole("button", { name: "Go to sign in" }));
    expect(screen.getByRole("form", { name: "Staff sign-in" })).toBeInTheDocument();
  });

  it("will not send a reset when the two passwords differ", async () => {
    installFakeApi({ "GET /auth/status": { body: { required: true, accounts: true } } });
    const user = userEvent.setup();
    renderPage(
      <AuthGate>
        <p>the app</p>
      </AuthGate>,
    );
    await user.click(await screen.findByRole("button", { name: "Forgot your password?" }));
    await user.type(screen.getByLabelText("Username"), "meera");
    await user.type(screen.getByLabelText("Reset code"), "K7QX-92MD");
    await user.type(
      screen.getByLabelText("New password (at least 8 characters)"),
      "a-brand-new-pass",
    );
    await user.type(screen.getByLabelText("New password again"), "something-else-1");
    expect(screen.getByText("The two passwords are not the same.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set new password" })).toBeDisabled();
  });

  it("does not offer a reset when the server uses one shared password", async () => {
    installFakeApi({ "GET /auth/status": { body: { required: true, accounts: false } } });
    renderPage(
      <AuthGate>
        <p>the app</p>
      </AuthGate>,
    );
    await screen.findByRole("form", { name: "Staff sign-in" });
    expect(screen.queryByRole("button", { name: "Forgot your password?" })).not.toBeInTheDocument();
  });

  it("changes your own password and signs you out", async () => {
    setSession({ token: "t", name: "Meera", role: "RECEPTIONIST" });
    const api = installFakeApi({ "POST /auth/change-password": { status: 204 } });
    const user = userEvent.setup();
    renderPage(<ChangePasswordDialog onClose={vi.fn()} />);
    await user.type(screen.getByLabelText("Current password"), "old-password-1");
    await user.type(
      screen.getByLabelText("New password (at least 8 characters)"),
      "new-password-22",
    );
    await user.type(screen.getByLabelText("New password again"), "new-password-22");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    await waitFor(() => expect(api.count("POST", "/auth/change-password")).toBe(1));
    expect(api.last("POST", "/auth/change-password")?.body).toEqual({
      current_password: "old-password-1",
      new_password: "new-password-22",
    });
    await waitFor(() => expect(getSession()).toBeNull());
  });

  it("says the password is wrong and stays on the form", async () => {
    installFakeApi({
      "GET /auth/status": { body: { required: true } },
      "POST /auth/login": apiError(401, "UNAUTHENTICATED", "The password is not correct."),
    });
    const user = userEvent.setup();
    renderPage(
      <AuthGate>
        <p>the app</p>
      </AuthGate>,
    );
    await user.type(await screen.findByLabelText("Your name"), "Meera");
    await user.type(screen.getByLabelText("Staff password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("The password is not correct.")).toBeInTheDocument();
    expect(screen.queryByText("the app")).not.toBeInTheDocument();
    expect(getSession()).toBeNull();
  });

  it("lets a signed-in person straight in after a reload", async () => {
    setSession({ token: "t.s", name: "Ravi" });
    installFakeApi({ "GET /auth/status": { body: { required: true } } });
    renderPage(
      <AuthGate>
        <p>the app</p>
      </AuthGate>,
    );
    expect(await screen.findByText("the app")).toBeInTheDocument();
  });

  it("shows a retryable error when the server cannot be asked", async () => {
    installFakeApi({ "GET /auth/status": apiError(503, "SERVICE_UNAVAILABLE", "busy") });
    renderPage(
      <AuthGate>
        <p>the app</p>
      </AuthGate>,
    );
    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("does not send an Authorization header when nobody is signed in", async () => {
    const api = installFakeApi({ "GET /doctors": { body: [] } });
    await request("GET", "/doctors");
    expect(api.last("GET", "/doctors")?.headers.has("authorization")).toBe(false);
  });
});

describe("the session store", () => {
  it("keeps working from memory when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    resetSessionCache();
    expect(getSession()).toBeNull();
    setSession({ token: "a.b", name: "Meera" });
    expect(getSession()?.name).toBe("Meera");
  });

  it("tells subscribers when the session changes", () => {
    resetSessionCache();
    const seen: (string | undefined)[] = [];
    // import inside the test to use the same module instance as the store above
    return import("../lib/authStore").then(({ subscribeSession }) => {
      const stop = subscribeSession(() => seen.push(getSession()?.name));
      setSession({ token: "a.b", name: "Meera" });
      setSession(null);
      stop();
      setSession({ token: "c.d", name: "Late" });
      expect(seen).toEqual(["Meera", undefined]);
    });
  });
});

describe("the error boundary", () => {
  class Bomb extends Component<{ children?: ReactNode }> {
    render(): ReactNode {
      throw new Error("boom");
    }
  }

  it("replaces a page that fails to draw with a message and a way out", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderPage(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("This page could not be shown");
    expect(screen.getByRole("button", { name: "Reload the page" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the day view" })).toBeInTheDocument();
  });

  it("leaves a healthy page alone", () => {
    renderPage(
      <ErrorBoundary>
        <p>fine</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("fine")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("logs what failed, so it can be reported", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderPage(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    );
    expect(log.mock.calls.some((call) => call[0] === "The page failed to draw")).toBe(true);
  });
});
