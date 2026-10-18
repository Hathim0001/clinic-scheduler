import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { resetSessionCache, setSession } from "../lib/authStore";
import { apiError, installFakeApi } from "../test/fakeApi";
import { renderPage } from "../test/utils";
import Staff from "./Staff";

const account = (over = {}) => ({
  id: 1,
  username: "meera",
  display_name: "Meera",
  role: "RECEPTIONIST",
  active: true,
  ...over,
});

beforeEach(() => {
  window.sessionStorage.clear();
  resetSessionCache();
  setSession(null);
});

const open = { "GET /auth/status": { body: { required: false, accounts: false } } };

describe("staff accounts", () => {
  it("lists accounts and creates a new one", async () => {
    const api = installFakeApi({
      ...open,
      "GET /staff": { body: [account()] },
      "POST /staff": { status: 201, body: account({ id: 2, username: "dev", role: "ADMIN" }) },
    });
    const user = userEvent.setup();
    renderPage(<Staff />);
    expect(await screen.findByText("meera")).toBeInTheDocument();

    const form = screen.getByRole("form", { name: "New staff account" });
    await user.type(within(form).getByLabelText("Username"), "dev");
    await user.type(within(form).getByLabelText("Name shown in the history"), "Dev Admin");
    await user.type(within(form).getByLabelText(/^Password/), "long-enough-pass");
    await user.selectOptions(within(form).getByLabelText("Role"), "ADMIN");
    await user.click(within(form).getByRole("button", { name: "Create account" }));

    expect(api.last("POST", "/staff")?.body).toEqual({
      username: "dev",
      display_name: "Dev Admin",
      password: "long-enough-pass",
      role: "ADMIN",
    });
  });

  it("switches an account off and changes a role", async () => {
    const api = installFakeApi({
      ...open,
      "GET /staff": { body: [account()] },
      "PATCH /staff/1": { body: account({ active: false }) },
    });
    const user = userEvent.setup();
    renderPage(<Staff />);
    await user.click(await screen.findByRole("button", { name: "Switch off meera" }));
    expect(api.last("PATCH", "/staff/1")?.body).toEqual({ active: false });
    await user.selectOptions(screen.getByLabelText("Role of meera"), "ADMIN");
    expect(api.last("PATCH", "/staff/1")?.body).toEqual({ role: "ADMIN" });
  });

  it("resets a password only once it is long enough", async () => {
    const api = installFakeApi({
      ...open,
      "GET /staff": { body: [account()] },
      "PATCH /staff/1": { body: account() },
    });
    const user = userEvent.setup();
    renderPage(<Staff />);
    await user.click(await screen.findByRole("button", { name: "Reset password for meera" }));
    const save = screen.getByRole("button", { name: "Save password" });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("New password for meera"), "brand-new-pass");
    await user.click(save);
    expect(api.last("PATCH", "/staff/1")?.body).toEqual({ password: "brand-new-pass" });
  });

  it("explains why the last administrator cannot be removed", async () => {
    installFakeApi({
      ...open,
      "GET /staff": { body: [account({ role: "ADMIN" })] },
      "PATCH /staff/1": apiError(409, "LAST_ADMIN", "last", {}),
    });
    const user = userEvent.setup();
    renderPage(<Staff />);
    await user.click(await screen.findByRole("button", { name: "Switch off meera" }));
    expect(await screen.findByText(/last active administrator/)).toBeInTheDocument();
  });

  it("tells a receptionist that this page is for administrators", async () => {
    setSession({ token: "t", name: "Meera", role: "RECEPTIONIST" });
    const api = installFakeApi({
      "GET /auth/status": { body: { required: true, accounts: true } },
    });
    renderPage(<Staff />);
    expect(
      await screen.findByText(/Only an administrator can manage staff accounts/),
    ).toBeVisible();
    expect(api.count("GET", "/staff")).toBe(0);
  });
});
