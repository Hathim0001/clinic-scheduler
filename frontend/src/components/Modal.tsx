import { useRef, type ReactNode } from "react";
import { useFocusTrap } from "../lib/useFocusTrap";

interface Props {
  /** The id of the heading inside, so the dialog has a name for screen readers. */
  labelledBy: string;
  onClose: () => void;
  children: ReactNode;
  /** Clicking the dimmed page behind closes it (on by default; off while a form is half-filled). */
  closeOnBackdrop?: boolean;
}

/**
 * A dialog that behaves like one: focus moves in, Tab stays inside, Escape and a click on the dimmed
 * page close it, and focus returns to the button that opened it.
 */
export function Modal({ labelledBy, onClose, children, closeOnBackdrop = true }: Props) {
  const dialog = useRef<HTMLDivElement>(null);
  useFocusTrap(dialog, true, onClose);
  return (
    <div
      className="overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (closeOnBackdrop && event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialog}
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
      >
        {children}
      </div>
    </div>
  );
}
