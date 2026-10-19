import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Modal } from "./Modal";

function Harness({ closeOnBackdrop = true }: { closeOnBackdrop?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Open it
      </button>
      <button type="button">Behind the dialog</button>
      {open && (
        <Modal labelledBy="t" onClose={() => setOpen(false)} closeOnBackdrop={closeOnBackdrop}>
          <h2 id="t">Are you sure?</h2>
          <button type="button">First</button>
          <button type="button">Last</button>
        </Modal>
      )}
    </div>
  );
}

describe("a dialog", () => {
  it("is named, takes focus when it opens and gives it back when it closes", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open it" });
    await user.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Are you sure?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "First" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("keeps Tab and Shift+Tab inside, wrapping around", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Open it" }));
    await user.tab();
    expect(screen.getByRole("button", { name: "Last" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "First" })).toHaveFocus(); // wrapped, not the page
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Last" })).toHaveFocus();
  });

  it("closes when the dimmed page behind is clicked, unless it is told not to", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Open it" }));
    await user.click(document.querySelector(".overlay") as HTMLElement);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    unmount();

    render(<Harness closeOnBackdrop={false} />);
    await user.click(screen.getByRole("button", { name: "Open it" }));
    await user.click(document.querySelector(".overlay") as HTMLElement);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("stops the page behind from scrolling while open", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Open it" }));
    expect(document.body).toHaveClass("no-scroll");
    await user.keyboard("{Escape}");
    expect(document.body).not.toHaveClass("no-scroll");
  });
});
