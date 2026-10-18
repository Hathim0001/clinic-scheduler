import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { NavMenu } from "./NavMenu";

const setup = () =>
  render(
    <MemoryRouter initialEntries={["/"]}>
      <NavMenu label="More" paths={["/reports"]} badge={2} badgeLabel="2 items need attention">
        <li>
          <a href="/reports">Report</a>
        </li>
      </NavMenu>
    </MemoryRouter>,
  );

describe("the More menu", () => {
  it("opens on press and shows the badge while closed", async () => {
    setup();
    const button = screen.getByRole("button", { name: /More/ });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByLabelText("2 items need attention")).toBeInTheDocument();
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Report" })).toBeInTheDocument();
  });

  it("closes on Escape and gives focus back to the button", async () => {
    setup();
    const button = screen.getByRole("button", { name: /More/ });
    await userEvent.click(button);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("link", { name: "Report" })).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it("closes on a click outside", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: /More/ }));
    await userEvent.click(document.body);
    expect(screen.queryByRole("link", { name: "Report" })).not.toBeInTheDocument();
  });
});
