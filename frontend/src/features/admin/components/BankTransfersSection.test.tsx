import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BankTransfersSection } from "./BankTransfersSection";
import { formatReservationDeadline, formatWaiting } from "./transfer-clocks";
import { formatArs } from "../../../lib/money";
import type { AdminPendingBankTransfer } from "../../../services/admin-orders-api";

function transfer(overrides: Partial<AdminPendingBankTransfer> = {}): AdminPendingBankTransfer {
  return {
    id: 18,
    order_id: 19,
    method: "bank_transfer",
    status: "pending",
    amount: 25990,
    currency: "ARS",
    external_ref: null,
    preference_id: null,
    reference: "ORDER-19-PAY-18",
    order_total: 25990,
    reservation_expires_at: null,
    customer: {
      id: 3,
      first_name: "Ana",
      last_name: "Perez",
      email: "ana@example.com",
      dni: null,
      phone: null,
      has_account: false
    },
    created_at: new Date().toISOString(),
    paid_at: null,
    ...overrides
  } as AdminPendingBankTransfer;
}

function renderSection(overrides: Partial<Parameters<typeof BankTransfersSection>[0]> = {}) {
  const props = {
    transfers: [transfer()],
    loading: false,
    error: "",
    success: "",
    confirmingPaymentId: null,
    confirmTransfer: vi.fn().mockResolvedValue(undefined),
    reload: vi.fn().mockResolvedValue(undefined),
    formatArs,
    ...overrides
  };
  render(<BankTransfersSection {...props} />);
  return props;
}

describe("BankTransfersSection", () => {
  it("shows the reference the customer was told to write", () => {
    // Without it the admin cannot tell which bank statement line pays which order.
    renderSection();

    expect(screen.getByText("ORDER-19-PAY-18")).toBeInTheDocument();
  });

  it("shows the exact amount, cents included", () => {
    renderSection();

    expect(screen.getByText(/\$ 259,90/)).toBeInTheDocument();
    expect(screen.queryByText(/\$ 260(?!,)/)).not.toBeInTheDocument();
  });

  it("prefills the amount field with something typeable back", () => {
    renderSection();

    expect(screen.getByLabelText(/Monto recibido/i)).toHaveValue("259,90");
  });

  it("shows the customer and the order", () => {
    renderSection();

    expect(screen.getByText(/Ana Perez \(ana@example.com\)/)).toBeInTheDocument();
    expect(screen.getByText(/Orden #19/)).toBeInTheDocument();
  });

  it("says when the stock reservation lapses, so the admin can prioritise", () => {
    const inThreeHours = new Date(Date.now() + 3 * 60 * 60 * 1000 + 60_000).toISOString();
    renderSection({ transfers: [transfer({ reservation_expires_at: inThreeHours })] });

    expect(screen.getByText(/vence en 3 h/)).toBeInTheDocument();
  });

  it("confirms with what was typed in that row", () => {
    const props = renderSection();

    fireEvent.change(screen.getByLabelText(/Referencia del comprobante/i), {
      target: { value: "0004-99887" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar pago" }));

    expect(props.confirmTransfer).toHaveBeenCalledWith(
      expect.objectContaining({ id: 18 }),
      "0004-99887",
      "259,90"
    );
  });

  it("tells the admin when there is nothing waiting", () => {
    renderSection({ transfers: [] });

    expect(screen.getByText("No hay transferencias pendientes.")).toBeInTheDocument();
  });

  it("surfaces the confirmation error", () => {
    renderSection({ error: "El monto recibido no coincide" });

    expect(screen.getByText("El monto recibido no coincide")).toBeInTheDocument();
  });
});

describe("BankTransfersSection — clocks", () => {
  const now = new Date("2026-07-22T12:00:00Z").getTime();

  it("reads the wait in hours and then in days", () => {
    expect(formatWaiting("2026-07-22T11:40:00Z", now)).toBe("hace menos de 1 h");
    expect(formatWaiting("2026-07-22T04:00:00Z", now)).toBe("hace 8 h");
    expect(formatWaiting("2026-07-20T10:00:00Z", now)).toBe("hace 2 d 2 h");
  });

  it("calls out a reservation that already lapsed", () => {
    expect(formatReservationDeadline("2026-07-22T11:00:00Z", now)).toBe("reserva vencida");
    expect(formatReservationDeadline("2026-07-22T12:30:00Z", now)).toBe("vence en menos de 1 h");
    expect(formatReservationDeadline("2026-07-23T18:00:00Z", now)).toBe("vence en 30 h");
    expect(formatReservationDeadline(null, now)).toBe("sin reserva activa");
  });
});
