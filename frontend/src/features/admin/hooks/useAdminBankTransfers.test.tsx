import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAdminBankTransfers } from "./useAdminBankTransfers";
import {
  listAdminPendingBankTransfers,
  registerAdminOrderManualPayment,
  type AdminPendingBankTransfer
} from "../../../services/admin-orders-api";

vi.mock("../../../services/admin-orders-api", () => ({
  listAdminPendingBankTransfers: vi.fn(),
  registerAdminOrderManualPayment: vi.fn()
}));

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
    reservation_expires_at: "2026-07-24T10:00:00Z",
    customer: {
      id: 3,
      first_name: "Ana",
      last_name: "Perez",
      email: "ana@example.com",
      dni: null,
      phone: null,
      has_account: false
    },
    created_at: "2026-07-22T10:00:00Z",
    paid_at: null,
    ...overrides
  } as AdminPendingBankTransfer;
}

async function renderQueue(rows: AdminPendingBankTransfer[]) {
  vi.mocked(listAdminPendingBankTransfers).mockResolvedValue(rows);
  const rendered = renderHook(() => useAdminBankTransfers({ adminSection: "transferencias" }));
  await waitFor(() => expect(rendered.result.current.transfers).toHaveLength(rows.length));
  return rendered;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useAdminBankTransfers", () => {
  it("does not fetch the queue while another admin section is open", () => {
    renderHook(() => useAdminBankTransfers({ adminSection: "catalogo" }));

    expect(listAdminPendingBankTransfers).not.toHaveBeenCalled();
  });

  it("puts the oldest transfer first, because it is the closest to being cancelled", async () => {
    const { result } = await renderQueue([
      transfer({ id: 2, order_id: 22, created_at: "2026-07-22T10:00:00Z" }),
      transfer({ id: 1, order_id: 11, created_at: "2026-07-20T10:00:00Z" })
    ]);

    expect(result.current.transfers.map((row) => row.id)).toEqual([1, 2]);
  });

  it("confirms the payment with the exact amount and the receipt reference", async () => {
    const row = transfer();
    const { result } = await renderQueue([row]);
    vi.mocked(registerAdminOrderManualPayment).mockResolvedValue({
      order: { id: 19, status: "paid" },
      payment: { id: 18 }
    } as never);

    await act(async () => {
      await result.current.confirmTransfer(row, "  0004-99887  ", "259,90");
    });

    expect(registerAdminOrderManualPayment).toHaveBeenCalledWith({
      order_id: 19,
      method: "bank_transfer",
      paid_amount: 25990,
      payment_ref: "0004-99887"
    });
    expect(result.current.success).toContain("Orden #19");
  });

  it("drops the confirmed row from the queue", async () => {
    // The queue means "still needs verifying": leaving it there invites a second
    // confirmation of money that was already accounted for.
    const row = transfer();
    const { result } = await renderQueue([row, transfer({ id: 20, order_id: 21 })]);
    vi.mocked(registerAdminOrderManualPayment).mockResolvedValue({
      order: { id: 19, status: "paid" },
      payment: { id: 18 }
    } as never);

    await act(async () => {
      await result.current.confirmTransfer(row, "0004-99887", "259,90");
    });

    expect(result.current.transfers.map((r) => r.id)).toEqual([20]);
  });

  it("refuses a mismatched amount and says what the right one is", async () => {
    // The old message just said the amount was invalid, leaving the admin to
    // guess -- which is exactly how a rounded display used to block a payment.
    const row = transfer({ amount: 25990 });
    const { result } = await renderQueue([row]);

    await act(async () => {
      await result.current.confirmTransfer(row, "0004-99887", "260");
    });

    expect(registerAdminOrderManualPayment).not.toHaveBeenCalled();
    expect(result.current.error).toContain("259,90");
    expect(result.current.transfers).toHaveLength(1);
  });

  it("requires the receipt reference", async () => {
    const row = transfer();
    const { result } = await renderQueue([row]);

    await act(async () => {
      await result.current.confirmTransfer(row, "   ", "259,90");
    });

    expect(registerAdminOrderManualPayment).not.toHaveBeenCalled();
    expect(result.current.error).toBe("La referencia del comprobante es obligatoria.");
  });

  it("keeps the row when the backend rejects the confirmation", async () => {
    const row = transfer();
    const { result } = await renderQueue([row]);
    vi.mocked(registerAdminOrderManualPayment).mockRejectedValue(new Error("boom"));

    await act(async () => {
      await result.current.confirmTransfer(row, "0004-99887", "259,90");
    });

    expect(result.current.transfers).toHaveLength(1);
    expect(result.current.error).not.toBe("");
    expect(result.current.confirmingPaymentId).toBeNull();
  });

  it("surfaces an error when the queue cannot be loaded", async () => {
    vi.mocked(listAdminPendingBankTransfers).mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() => useAdminBankTransfers({ adminSection: "transferencias" }));

    await waitFor(() =>
      expect(result.current.error).toBe("No se pudieron cargar las transferencias pendientes.")
    );
  });
});
