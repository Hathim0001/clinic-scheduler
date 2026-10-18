import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { apiError, installFakeApi } from "../test/fakeApi";
import { clockInfo, renderPage } from "../test/utils";
import Proof from "./Proof";

const caseOf = (id: string, passed = true) => ({
  id,
  rule: `Rule ${id}`,
  scenario: "Do a thing",
  expected: "SLOT_TAKEN",
  observed: passed ? "SLOT_TAKEN" : "ACCEPTED",
  passed,
});

describe("prove the rules", () => {
  it("runs the scenarios on request and shows that nothing was kept", async () => {
    const api = installFakeApi({
      "GET /clock": { body: clockInfo() },
      "POST /diagnostics/proof": {
        body: { passed: true, rows_before: 12, rows_after: 12, cases: [caseOf("a"), caseOf("b")] },
      },
    });
    const user = userEvent.setup();
    renderPage(<Proof />);
    expect(api.count("POST", "/diagnostics/proof")).toBe(0); // never runs by itself

    await user.click(screen.getByRole("button", { name: "Run the proof" }));

    expect(await screen.findByText(/All 2 scenarios gave the documented answer/)).toBeVisible();
    expect(screen.getByText(/Rows before the run: 12, after: 12 \(nothing kept\)/)).toBeVisible();
    expect(screen.getAllByText("Pass")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Run it again" })).toBeEnabled();
  });

  it("flags a scenario that did not give the documented answer", async () => {
    installFakeApi({
      "GET /clock": { body: clockInfo() },
      "POST /diagnostics/proof": {
        body: {
          passed: false,
          rows_before: 5,
          rows_after: 5,
          cases: [caseOf("a"), caseOf("b", false)],
        },
      },
    });
    const user = userEvent.setup();
    renderPage(<Proof />);
    await user.click(screen.getByRole("button", { name: "Run the proof" }));
    expect(await screen.findByText(/1 of 2 scenarios did not/)).toBeVisible();
    expect(screen.getByText("FAIL")).toBeVisible();
  });

  it("shows the error when the server cannot run it", async () => {
    installFakeApi({
      "GET /clock": { body: clockInfo() },
      "POST /diagnostics/proof": apiError(503, "SERVICE_UNAVAILABLE", "The database is busy."),
    });
    const user = userEvent.setup();
    renderPage(<Proof />);
    await user.click(screen.getByRole("button", { name: "Run the proof" }));
    expect(await screen.findByRole("alert")).toBeVisible();
  });
});
