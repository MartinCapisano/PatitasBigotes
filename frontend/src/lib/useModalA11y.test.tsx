import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useModalA11y } from "./useModalA11y";

function TestModal({ onClose }: { onClose: () => void }) {
  const containerRef = useModalA11y<HTMLDivElement>(true, onClose);
  return (
    <div ref={containerRef} role="dialog" aria-modal="true" tabIndex={-1}>
      <button type="button">Cerrar</button>
      <input type="text" placeholder="middle" />
      <button type="button">Confirmar</button>
    </div>
  );
}

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Abrir
      </button>
      {open ? <TestModal onClose={() => setOpen(false)} /> : null}
    </div>
  );
}

describe("useModalA11y", () => {
  it("autofocuses the first focusable element on open", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Abrir"));

    expect(screen.getByText("Cerrar")).toHaveFocus();
  });

  it("calls onClose on Escape", () => {
    const onClose = vi.fn();
    function Wrapper() {
      const containerRef = useModalA11y<HTMLDivElement>(true, onClose);
      return (
        <div ref={containerRef} role="dialog" tabIndex={-1}>
          <button type="button">Cerrar</button>
        </div>
      );
    }
    render(<Wrapper />);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("traps Tab focus cycling from the last back to the first element", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Abrir"));

    screen.getByText("Confirmar").focus();
    fireEvent.keyDown(document, { key: "Tab" });

    expect(screen.getByText("Cerrar")).toHaveFocus();
  });

  it("traps Shift+Tab focus cycling from the first back to the last element", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Abrir"));

    screen.getByText("Cerrar").focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    expect(screen.getByText("Confirmar")).toHaveFocus();
  });

  it("returns focus to the trigger element after closing", () => {
    render(<Harness />);
    const openButton = screen.getByText("Abrir");
    openButton.focus();
    fireEvent.click(openButton);
    expect(screen.getByText("Cerrar")).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(openButton).toHaveFocus();
  });
});
