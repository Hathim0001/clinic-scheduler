import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import { apiError, installFakeApi } from "../test/fakeApi";
import {
  appointment,
  clockInfo,
  flaggedDeposit,
  noDeposit,
  patient,
  renderPage,
} from "../test/utils";
import { PatientDetail, PatientSearch } from "./Patients";

const routes = (extra = {}) => ({ "GET /clock": { body: clockInfo() }, ...extra });

const searchPage = (
  <Routes>
    <Route path="/patients" element={<PatientSearch />} />
    <Route path="/patients/:id" element={<PatientDetail />} />
  </Routes>
);

const page = (items: unknown[]) => ({
  body: { items, total: items.length, limit: 10, offset: 0 },
});

describe("finding patients", () => {
  it("searches by phone when the text looks like a phone number", async () => {
    const api = installFakeApi(routes({ "GET /patients": page([patient({ deposit: null })]) }));
    const user = userEvent.setup();
    renderPage(searchPage, "/patients");

    await user.type(screen.getByLabelText("Find a patient by phone or name"), "98765 43210");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("Kavita Nair")).toBeInTheDocument();
    expect(api.last("GET", "/patients")?.query).toEqual({ phone: "98765 43210", limit: "10" });
  });

  it("searches by the start of the name otherwise", async () => {
    const api = installFakeApi(routes({ "GET /patients": page([patient({ deposit: null })]) }));
    const user = userEvent.setup();
    renderPage(searchPage, "/patients");

    await user.type(screen.getByLabelText("Find a patient by phone or name"), "Kav");
    await user.click(screen.getByRole("button", { name: "Search" }));

    await screen.findByText("Kavita Nair");
    expect(api.last("GET", "/patients")?.query).toEqual({ q: "Kav", limit: "10" });
  });

  it("registers a new patient from an empty result and opens them", async () => {
    const created = patient({ id: 9, name: "Asha Iyer", phone: "+919876543210" });
    const api = installFakeApi(
      routes({
        "GET /patients": page([]),
        "POST /patients": { status: 201, body: created },
        "GET /patients/9": { body: created },
        "GET /patients/9/appointments": { body: { items: [], total: 0, limit: 50, offset: 0 } },
      }),
    );
    const user = userEvent.setup();
    renderPage(searchPage, "/patients");

    await user.type(screen.getByLabelText("Find a patient by phone or name"), "98765 43210");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.click(await screen.findByRole("button", { name: "Register a new patient" }));

    const form = screen.getByRole("form", { name: "New patient" });
    expect(within(form).getByLabelText("Phone")).toHaveValue("98765 43210"); // carried over
    await user.type(within(form).getByLabelText("Name"), "Asha Iyer");
    await user.type(within(form).getByLabelText("Date of birth"), "1985-04-02");
    await user.click(within(form).getByRole("button", { name: "Register patient" }));

    await waitFor(() =>
      expect(api.last("POST", "/patients")?.body).toEqual({
        name: "Asha Iyer",
        phone: "98765 43210",
        date_of_birth: "1985-04-02",
      }),
    );
    expect(await screen.findByRole("heading", { name: "Asha Iyer" })).toBeInTheDocument();
  });

  it("says plainly when the phone number is already registered", async () => {
    installFakeApi(
      routes({
        "GET /patients": page([]),
        "POST /patients": apiError(
          409,
          "PHONE_TAKEN",
          "This phone number is already registered to Asha Iyer. Confirm to share it.",
          {
            patient_id: 3,
            patients: [{ patient_id: 3, name: "Asha Iyer", date_of_birth: "1985-04-02" }],
          },
        ),
      }),
    );
    const user = userEvent.setup();
    renderPage(searchPage, "/patients");
    await user.click(screen.getByRole("button", { name: "New patient" }));
    const form = screen.getByRole("form", { name: "New patient" });
    await user.type(within(form).getByLabelText("Name"), "Asha Iyer");
    await user.type(within(form).getByLabelText("Phone"), "9876543210");
    await user.type(within(form).getByLabelText("Date of birth"), "1985-04-02");
    await user.click(within(form).getByRole("button", { name: "Register patient" }));
    expect(await screen.findByText(/already registered to:/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use Asha Iyer" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Register as a family member on this number" }),
    ).toBeInTheDocument();
  });
});

describe("a patient's page", () => {
  const detailRoutes = (deposit = noDeposit) =>
    routes({
      "GET /patients/7": { body: patient({ deposit }) },
      "GET /patients/7/appointments": {
        body: {
          items: [
            appointment({ id: 2, status: "BOOKED" }),
            appointment({ id: 1, status: "NO_SHOW", allowed_actions: [] }),
          ],
          total: 2,
          limit: 50,
          offset: 0,
        },
      },
    });

  it("explains a deposit flag with the strikes and the date it ends", async () => {
    installFakeApi(detailRoutes(flaggedDeposit));
    renderPage(searchPage, "/patients/7");
    const card = await screen.findByRole("region", { name: "Deposit status" });
    expect(card).toHaveTextContent("Deposit required until 27 Nov 2026, 15:10 IST.");
    expect(card).toHaveTextContent("No-show on 29 Oct 2026, 10:00 IST (appointment #12)");
    expect(card).toHaveTextContent("Late cancellation on 28 Oct 2026, 15:10 IST (appointment #9)");
  });

  it("says there is no flag for a patient without strikes", async () => {
    installFakeApi(detailRoutes());
    renderPage(searchPage, "/patients/7");
    expect(
      await screen.findByText(/No late cancellations or no-shows in the last 30 days/),
    ).toBeInTheDocument();
  });

  it("lists the history with the buttons only where they apply", async () => {
    installFakeApi(detailRoutes());
    renderPage(searchPage, "/patients/7");
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(
      within(rows[0] as HTMLElement).getByRole("button", { name: "Reschedule" }),
    ).toBeEnabled();
    expect(
      within(rows[1] as HTMLElement).getByRole("button", { name: "Reschedule" }),
    ).toBeDisabled();
    expect(
      within(rows[1] as HTMLElement).getByText("No-show", { selector: "span.status" }),
    ).toBeInTheDocument();
  });

  it("links to booking for this patient", async () => {
    installFakeApi(detailRoutes());
    renderPage(searchPage, "/patients/7");
    expect(
      await screen.findByRole("link", { name: "Book an appointment for this patient" }),
    ).toHaveAttribute("href", "/book?patient=7");
  });

  it("shows a not-found message for an unknown patient", async () => {
    installFakeApi(
      routes({
        "GET /patients/99": apiError(404, "PATIENT_NOT_FOUND", "There is no patient with id 99."),
        "GET /patients/99/appointments": apiError(
          404,
          "PATIENT_NOT_FOUND",
          "There is no patient with id 99.",
        ),
      }),
    );
    renderPage(searchPage, "/patients/99");
    expect(await screen.findByRole("alert")).toHaveTextContent("There is no patient with id 99.");
  });
});
