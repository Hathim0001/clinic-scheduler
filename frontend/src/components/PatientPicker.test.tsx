import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { installFakeApi } from "../test/fakeApi";
import { clockInfo, patient, renderPage } from "../test/utils";
import { PatientPicker } from "./PatientPicker";

const people = (n: number) =>
  Array.from({ length: n }, (_, index) =>
    patient({
      id: index + 1,
      name: `Asha ${index + 1}`,
      phone: `+9190000000${String(index).padStart(2, "0")}`,
      deposit: null,
    }),
  );

describe("finding more patients", () => {
  it("offers 'Show more' when the search has more results than are shown, and loads the next ten", async () => {
    const api = installFakeApi({
      "GET /clock": { body: clockInfo() },
      "GET /patients": (call) => {
        const limit = Number(call.query.limit);
        return { body: { items: people(Math.min(limit, 25)), total: 25, limit, offset: 0 } };
      },
    });
    const user = userEvent.setup();
    renderPage(<PatientPicker onSelect={() => undefined} />);
    await user.type(screen.getByLabelText("Find a patient by phone or name"), "Asha");
    await user.click(screen.getByRole("button", { name: "Search" }));

    const more = await screen.findByRole("button", { name: "Show more (10 of 25)" });
    await user.click(more);
    expect(await screen.findByRole("button", { name: "Show more (20 of 25)" })).toBeInTheDocument();
    expect(api.last("GET", "/patients")?.query.limit).toBe("20");
    await user.click(screen.getByRole("button", { name: "Show more (20 of 25)" }));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /Show more/ })).not.toBeInTheDocument(),
    );
    expect(screen.getAllByRole("button", { name: /^Asha/ })).toHaveLength(25);
  });

  it("does not offer 'Show more' when everything fits", async () => {
    installFakeApi({
      "GET /clock": { body: clockInfo() },
      "GET /patients": { body: { items: people(3), total: 3, limit: 10, offset: 0 } },
    });
    const user = userEvent.setup();
    renderPage(<PatientPicker onSelect={() => undefined} />);
    await user.type(screen.getByLabelText("Find a patient by phone or name"), "Asha{Enter}");
    expect(await screen.findByRole("button", { name: "Asha 1" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Show more/ })).not.toBeInTheDocument();
  });

  it("starts again from ten when a new search is made", async () => {
    const api = installFakeApi({
      "GET /clock": { body: clockInfo() },
      "GET /patients": (call) => {
        const limit = Number(call.query.limit);
        return { body: { items: people(Math.min(limit, 25)), total: 25, limit, offset: 0 } };
      },
    });
    const user = userEvent.setup();
    renderPage(<PatientPicker onSelect={() => undefined} />);
    const box = screen.getByLabelText("Find a patient by phone or name");
    await user.type(box, "Asha{Enter}");
    await user.click(await screen.findByRole("button", { name: "Show more (10 of 25)" }));
    await screen.findByRole("button", { name: "Show more (20 of 25)" });
    await user.clear(box);
    await user.type(box, "Ravi{Enter}");
    await waitFor(() => expect(api.last("GET", "/patients")?.query.q).toBe("Ravi"));
    expect(api.last("GET", "/patients")?.query.limit).toBe("10");
  });
});
