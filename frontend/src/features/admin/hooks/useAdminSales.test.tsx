import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAdminSales } from "./useAdminSales";
import {
  createAdminSale,
  searchAdminUsers,
  type AdminSearchUser,
  type CreateAdminSaleResponse,
} from "../../../services/admin-sales-api";
import type { AdminProduct, AdminVariant } from "../../../services/admin-catalog-api";

// T-05 (docs/16_Testing.md §6) — `useAdminSales.onSubmit`: la venta presencial.
// El riesgo que cubre es "venta presencial mal registrada": que el payload enviado
// al backend no refleje lo que el admin cargó (cliente, ítems, pago). Por eso los
// tests afirman sobre el ARGUMENTO exacto de `createAdminSale`, no solo que se llamó.
vi.mock("../../../services/admin-sales-api", () => ({
  createAdminSale: vi.fn(),
  searchAdminUsers: vi.fn(),
}));

function product(overrides: Partial<AdminProduct> = {}): AdminProduct {
  return {
    id: 1,
    name: "Collar",
    description: null,
    min_var_price: 5000,
    category: "Accesorios",
    category_id: 1,
    stock: 10,
    active: true,
    ...overrides,
  };
}

function variant(overrides: Partial<AdminVariant> = {}): AdminVariant {
  return {
    id: 10,
    product_id: 1,
    sku: "COL-1",
    size: "M",
    color: "Azul",
    price: 5000,
    stock: 10,
    active: true,
    ...overrides,
  };
}

function foundUser(overrides: Partial<AdminSearchUser> = {}): AdminSearchUser {
  return {
    id: 7,
    first_name: "Ana",
    last_name: "Gómez",
    email: "ana@example.com",
    dni: "30111222",
    phone: "1155667788",
    has_account: true,
    ...overrides,
  };
}

function saleResponse(id: number, status: string): CreateAdminSaleResponse {
  return { order: { id, status } } as unknown as CreateAdminSaleResponse;
}

function makeParams() {
  return {
    adminSection: "sales" as const,
    productsSorted: [product()],
    variantsByProduct: { 1: [variant()] },
  };
}

function submitEvent() {
  return { preventDefault: vi.fn() } as unknown as React.FormEvent;
}

// Reproduce el flujo de UI para dejar un ítem en el borrador: elegir producto,
// tipear variante + cantidad y agregar. Pasa por `onAddItem`, que es como el
// componente real arma `items`.
function addItem(
  result: { current: ReturnType<typeof useAdminSales> },
  variantId: number,
  quantity: number,
) {
  // El toggle y el confirm van en `act()`s separados a propósito: `onConfirmPendingProduct`
  // lee `pendingSelectedProductId`, que recién queda seteado tras re-renderizar.
  act(() => {
    result.current.onTogglePendingProduct(1, true);
  });
  act(() => {
    result.current.onConfirmPendingProduct();
  });
  act(() => {
    result.current.setNewVariantId(String(variantId));
    result.current.setNewQuantity(String(quantity));
  });
  act(() => {
    result.current.onAddItem();
  });
}

function fillNewCustomer(result: { current: ReturnType<typeof useAdminSales> }) {
  act(() => {
    result.current.setFirstName("  Juan  ");
    result.current.setLastName("  Pérez  ");
    result.current.setEmail("  juan@example.com  ");
    result.current.setPhone("  1144556677  ");
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useAdminSales.onSubmit — guards (no llama al backend)", () => {
  it("rechaza el submit sin ítems", async () => {
    const { result } = renderHook(() => useAdminSales(makeParams()));
    fillNewCustomer(result);

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    expect(createAdminSale).not.toHaveBeenCalled();
    expect(result.current.error).toBe("Agrega al menos un producto.");
  });

  it("rechaza un cliente nuevo con datos incompletos", async () => {
    const { result } = renderHook(() => useAdminSales(makeParams()));
    addItem(result, 10, 1);
    // email y teléfono vacíos → falta info del cliente nuevo
    act(() => {
      result.current.setFirstName("Juan");
      result.current.setLastName("Pérez");
    });

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    expect(createAdminSale).not.toHaveBeenCalled();
    expect(result.current.error).toBe(
      "Completa nombre, apellido, email y telefono o selecciona un usuario existente.",
    );
  });

  it("rechaza registrar pago sin monto pagado", async () => {
    const { result } = renderHook(() => useAdminSales(makeParams()));
    addItem(result, 10, 1);
    fillNewCustomer(result);
    act(() => {
      result.current.setRegisterPayment(true);
    });

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    expect(createAdminSale).not.toHaveBeenCalled();
    expect(result.current.error).toBe("Ingresa el monto pagado.");
  });
});

describe("useAdminSales.onSubmit — payload correcto", () => {
  it("cliente nuevo sin pago: manda customer 'new' con datos trimmeados, dni null e ítems mapeados", async () => {
    vi.mocked(createAdminSale).mockResolvedValue(saleResponse(42, "submitted"));
    const { result } = renderHook(() => useAdminSales(makeParams()));
    addItem(result, 10, 2);
    fillNewCustomer(result);

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    expect(createAdminSale).toHaveBeenCalledTimes(1);
    expect(createAdminSale).toHaveBeenCalledWith({
      customer: {
        mode: "new",
        first_name: "Juan",
        last_name: "Pérez",
        email: "juan@example.com",
        phone: "1144556677",
        dni: null,
      },
      items: [{ variant_id: 10, quantity: 2 }],
      register_payment: false,
      payment: undefined,
    });
    expect(result.current.success).toBe(
      "Orden registrada. Orden #42 en estado submitted.",
    );
    // El borrador se limpia tras registrar, para no re-cargar la misma venta.
    expect(result.current.items).toEqual([]);
  });

  it("usuario existente + pago en efectivo: customer 'existing' y payment con vuelto", async () => {
    vi.mocked(createAdminSale).mockResolvedValue(saleResponse(99, "paid"));
    const { result } = renderHook(() => useAdminSales(makeParams()));
    addItem(result, 10, 1);
    act(() => {
      result.current.onTogglePendingUser(foundUser(), true);
    });
    act(() => {
      result.current.onConfirmPendingUser();
    });
    act(() => {
      result.current.setRegisterPayment(true);
      result.current.setPaymentMethod("cash");
      result.current.setAmountPaid("6000");
      result.current.setChangeAmount("1000");
      result.current.setPaymentRef("  TICKET-1  ");
    });

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    expect(createAdminSale).toHaveBeenCalledWith({
      customer: { mode: "existing", user_id: 7 },
      items: [{ variant_id: 10, quantity: 1 }],
      register_payment: true,
      payment: {
        method: "cash",
        amount_paid: 6000,
        change_amount: 1000,
        payment_ref: "TICKET-1",
      },
    });
    expect(result.current.success).toBe(
      "Venta registrada. Orden #99 en estado paid.",
    );
  });

  it("transferencia bancaria: no manda change_amount (queda undefined)", async () => {
    vi.mocked(createAdminSale).mockResolvedValue(saleResponse(100, "paid"));
    const { result } = renderHook(() => useAdminSales(makeParams()));
    addItem(result, 10, 1);
    fillNewCustomer(result);
    act(() => {
      result.current.setRegisterPayment(true);
      result.current.setPaymentMethod("bank_transfer");
      result.current.setAmountPaid("5000");
      result.current.setChangeAmount("1000"); // debe ignorarse en transferencia
    });

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    const payload = vi.mocked(createAdminSale).mock.calls[0][0];
    expect(payload.payment).toEqual({
      method: "bank_transfer",
      amount_paid: 5000,
      change_amount: undefined,
      payment_ref: undefined,
    });
  });
});

describe("useAdminSales.onSubmit — error del backend", () => {
  it("muestra el detail del backend (p. ej. stock insuficiente) y libera el saving", async () => {
    vi.mocked(createAdminSale).mockRejectedValue({
      response: { status: 409, data: { detail: "insufficient stock" } },
    });
    const { result } = renderHook(() => useAdminSales(makeParams()));
    addItem(result, 10, 1);
    fillNewCustomer(result);

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    await waitFor(() => {
      expect(result.current.error).toBe("insufficient stock");
    });
    expect(result.current.saving).toBe(false);
    expect(result.current.success).toBe("");
  });
});
