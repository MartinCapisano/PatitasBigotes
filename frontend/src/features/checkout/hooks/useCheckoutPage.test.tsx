import type { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCheckoutPage } from "./useCheckoutPage";
import type { CartItem } from "../../../lib/cart-storage";
import {
  clearCart,
  incrementCartItem,
  readCart,
  removeCartItem,
} from "../../../lib/cart-storage";
import {
  getMercadoPagoCheckoutUrl,
  redirectToMercadoPago,
  submitAuthenticatedCheckoutFromCart,
  submitGuestCheckoutFromCart,
} from "../../../services/checkout-api";

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: vi.fn(actual.useNavigate) };
});

vi.mock("../../../lib/cart-storage", async () => {
  const actual = await vi.importActual<typeof import("../../../lib/cart-storage")>(
    "../../../lib/cart-storage"
  );
  return {
    ...actual,
    readCart: vi.fn(),
    clearCart: vi.fn(),
    incrementCartItem: vi.fn(),
    decrementCartItem: vi.fn(),
    removeCartItem: vi.fn(),
  };
});

// Only the network calls are stubbed. `lib/bank-transfer` is left alone: it is
// a pure reader of the payment payload, and the point here is what the hook
// does with its result.
vi.mock("../../../services/checkout-api", async () => {
  const actual = await vi.importActual<typeof import("../../../services/checkout-api")>(
    "../../../services/checkout-api"
  );
  return {
    ...actual,
    submitGuestCheckoutFromCart: vi.fn(),
    submitAuthenticatedCheckoutFromCart: vi.fn(),
    getMercadoPagoCheckoutUrl: vi.fn(),
    redirectToMercadoPago: vi.fn(),
  };
});

const TRANSFER_INSTRUCTIONS = {
  alias: "patitas.bigotes.real",
  cbu: "0110599520000012345678",
  bank_name: "Banco Nacion",
  holder: "Martin Capisano",
  tax_id: "20-35123456-7",
  reference: "ORDER-42-PAY-7",
  amount: 10000,
  currency: "ARS",
  whatsapp_number: "5493511234567",
  whatsapp_url: "https://wa.me/5493511234567?text=Referencia%3A%20ORDER-42-PAY-7",
};

function wrapper() {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <MemoryRouter initialEntries={["/checkout"]}>{children}</MemoryRouter>;
  };
}

function cartItem(overrides: Partial<CartItem> = {}): CartItem {
  return {
    product_id: 1,
    product_name: "Collar",
    variant_id: 10,
    option_label: "Rojo / S",
    unit_price: 5000,
    quantity: 2,
    img_url: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useNavigate).mockReturnValue(vi.fn());
  vi.mocked(readCart).mockReturnValue([cartItem()]);
});

describe("useCheckoutPage", () => {
  it("computes the cart total from item price times quantity", () => {
    vi.mocked(readCart).mockReturnValue([
      cartItem({ variant_id: 10, unit_price: 5000, quantity: 2 }),
      cartItem({ variant_id: 11, unit_price: 1500, quantity: 3 }),
    ]);

    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: false }),
      { wrapper: wrapper() }
    );

    expect(result.current.total).toBe(5000 * 2 + 1500 * 3);
  });

  it("submits a guest bank_transfer checkout, clears the cart and shows the order in the success message", async () => {
    vi.mocked(submitGuestCheckoutFromCart).mockResolvedValue({
      order: { id: 42, status: "submitted", total_amount: 10000, items: [{ id: 1 }] },
      payment: { id: 7, method: "bank_transfer", status: "pending", amount: 10000, currency: "ARS" },
    });

    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: false }),
      { wrapper: wrapper() }
    );

    await act(async () => {
      await result.current.onFinalizeCheckout();
    });

    expect(submitGuestCheckoutFromCart).toHaveBeenCalledTimes(1);
    expect(submitAuthenticatedCheckoutFromCart).not.toHaveBeenCalled();
    expect(clearCart).toHaveBeenCalledTimes(1);
    expect(result.current.success).toContain("Orden #42");
    expect(result.current.error).toBe("");
  });

  it("hands the guest the transfer instructions instead of a plain confirmation", async () => {
    vi.mocked(submitGuestCheckoutFromCart).mockResolvedValue({
      order: { id: 42, status: "submitted", total_amount: 10000, items: [{ id: 1 }] },
      payment: {
        id: 7,
        method: "bank_transfer",
        status: "pending",
        amount: 10000,
        currency: "ARS",
        provider_payload_data: { instructions: TRANSFER_INSTRUCTIONS },
      },
    });

    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: false }),
      { wrapper: wrapper() }
    );

    await act(async () => {
      await result.current.onFinalizeCheckout();
    });

    expect(result.current.bankTransfer).toEqual({
      orderId: 42,
      instructions: TRANSFER_INSTRUCTIONS,
      publicStatusToken: null,
    });
    expect(result.current.success).toBe("");
    expect(clearCart).toHaveBeenCalledTimes(1);
  });

  it("hands the logged-in shopper the same instructions as the guest", async () => {
    vi.mocked(submitAuthenticatedCheckoutFromCart).mockResolvedValue({
      order: { id: 99, status: "submitted", total_amount: 10000, items: [{ id: 1 }] },
      payment: {
        id: 8,
        method: "bank_transfer",
        status: "pending",
        amount: 10000,
        currency: "ARS",
        provider_payload_data: { instructions: TRANSFER_INSTRUCTIONS },
      },
    });

    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: true }),
      { wrapper: wrapper() }
    );

    await act(async () => {
      await result.current.onFinalizeCheckout();
    });

    expect(result.current.bankTransfer).toEqual({
      orderId: 99,
      instructions: TRANSFER_INSTRUCTIONS,
      publicStatusToken: null,
    });
  });

  it("carries the public token so a guest keeps a way back to the instructions", async () => {
    vi.mocked(submitGuestCheckoutFromCart).mockResolvedValue({
      order: { id: 42, status: "submitted", total_amount: 10000, items: [{ id: 1 }] },
      payment: {
        id: 7,
        method: "bank_transfer",
        status: "pending",
        amount: 10000,
        currency: "ARS",
        public_status_token: "tok-invitado-42",
        provider_payload_data: { instructions: TRANSFER_INSTRUCTIONS },
      },
    });

    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: false }),
      { wrapper: wrapper() }
    );

    await act(async () => {
      await result.current.onFinalizeCheckout();
    });

    expect(result.current.bankTransfer?.publicStatusToken).toBe("tok-invitado-42");
  });

  it("falls back to the plain confirmation when the instructions come incomplete", async () => {
    // Better a bare confirmation than a screen with a blank CBU next to an
    // amount: the customer could transfer into the void.
    const withoutCbu: Partial<typeof TRANSFER_INSTRUCTIONS> = { ...TRANSFER_INSTRUCTIONS };
    delete withoutCbu.cbu;
    vi.mocked(submitGuestCheckoutFromCart).mockResolvedValue({
      order: { id: 42, status: "submitted", total_amount: 10000, items: [{ id: 1 }] },
      payment: {
        id: 7,
        method: "bank_transfer",
        status: "pending",
        amount: 10000,
        currency: "ARS",
        provider_payload_data: { instructions: withoutCbu },
      },
    });

    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: false }),
      { wrapper: wrapper() }
    );

    await act(async () => {
      await result.current.onFinalizeCheckout();
    });

    expect(result.current.bankTransfer).toBeNull();
    expect(result.current.success).toContain("Orden #42");
  });

  it("uses the authenticated checkout endpoint when the shopper is logged in", async () => {
    vi.mocked(submitAuthenticatedCheckoutFromCart).mockResolvedValue({
      order: { id: 99, status: "submitted", total_amount: 10000, items: [{ id: 1 }] },
      payment: { id: 8, method: "bank_transfer", status: "pending", amount: 10000, currency: "ARS" },
    });

    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: true }),
      { wrapper: wrapper() }
    );

    await act(async () => {
      await result.current.onFinalizeCheckout();
    });

    expect(submitAuthenticatedCheckoutFromCart).toHaveBeenCalledTimes(1);
    expect(submitGuestCheckoutFromCart).not.toHaveBeenCalled();
    expect(result.current.success).toContain("Orden #99");
  });

  it("redirects to MercadoPago and clears the cart when a checkout URL is returned", async () => {
    act(() => undefined);
    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: false }),
      { wrapper: wrapper() }
    );
    act(() => {
      result.current.setPaymentMethod("mercadopago");
    });

    vi.mocked(submitGuestCheckoutFromCart).mockResolvedValue({
      order: { id: 5, status: "submitted", total_amount: 10000, items: [{ id: 1 }] },
      payment: { id: 9, method: "mercadopago", status: "pending", amount: 10000, currency: "ARS" },
    });
    vi.mocked(getMercadoPagoCheckoutUrl).mockReturnValue("https://mercadopago.com/checkout/abc");

    await act(async () => {
      await result.current.onFinalizeCheckout();
    });

    expect(clearCart).toHaveBeenCalledTimes(1);
    expect(redirectToMercadoPago).toHaveBeenCalledWith("https://mercadopago.com/checkout/abc");
  });

  it("errors without clearing the cart when MercadoPago returns no checkout URL", async () => {
    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: false }),
      { wrapper: wrapper() }
    );
    act(() => {
      result.current.setPaymentMethod("mercadopago");
    });

    vi.mocked(submitGuestCheckoutFromCart).mockResolvedValue({
      order: { id: 5, status: "submitted", total_amount: 10000, items: [{ id: 1 }] },
      payment: { id: 9, method: "mercadopago", status: "pending", amount: 10000, currency: "ARS" },
    });
    vi.mocked(getMercadoPagoCheckoutUrl).mockReturnValue(null);

    await act(async () => {
      await result.current.onFinalizeCheckout();
    });

    expect(redirectToMercadoPago).not.toHaveBeenCalled();
    expect(clearCart).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(result.current.error).not.toBe("");
    });
  });

  it("redirects a guest to /login with cart context when the email already has an account", async () => {
    const navigateSpy = vi.fn();
    vi.mocked(useNavigate).mockReturnValue(navigateSpy);
    vi.mocked(submitGuestCheckoutFromCart).mockRejectedValue({
      response: { status: 409, data: { detail: "registered account requires login" } },
    });

    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: false }),
      { wrapper: wrapper() }
    );
    act(() => {
      result.current.setGuestEmail("shopper@example.com");
    });

    await act(async () => {
      await result.current.onFinalizeCheckout();
    });

    expect(navigateSpy).toHaveBeenCalledWith("/login", {
      state: {
        from: "/checkout",
        checkoutEmail: "shopper@example.com",
        reason: "registered_account_checkout",
      },
    });
    expect(result.current.error).toBe("");
  });

  it("shows an error message and keeps the cart when the checkout API fails generically", async () => {
    vi.mocked(submitGuestCheckoutFromCart).mockRejectedValue({
      response: { status: 500, data: {} },
    });

    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: false }),
      { wrapper: wrapper() }
    );

    await act(async () => {
      await result.current.onFinalizeCheckout();
    });

    await waitFor(() => {
      expect(result.current.error).not.toBe("");
    });
    expect(clearCart).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
  });

  it("does nothing when finalizing an empty cart", async () => {
    vi.mocked(readCart).mockReturnValue([]);

    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: false }),
      { wrapper: wrapper() }
    );

    await act(async () => {
      await result.current.onFinalizeCheckout();
    });

    expect(submitGuestCheckoutFromCart).not.toHaveBeenCalled();
    expect(submitAuthenticatedCheckoutFromCart).not.toHaveBeenCalled();
  });

  it("blocks incrementing above the max quantity of 10 and surfaces an error", () => {
    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: false }),
      { wrapper: wrapper() }
    );

    act(() => {
      result.current.onIncrementItem(10, 10);
    });

    expect(incrementCartItem).not.toHaveBeenCalled();
    expect(result.current.error).toContain("10");
  });

  it("ignores remove actions while a checkout is in flight", async () => {
    type SubmitResult = Awaited<ReturnType<typeof submitGuestCheckoutFromCart>>;
    let resolveSubmit: (value: SubmitResult) => void = () => undefined;
    vi.mocked(submitGuestCheckoutFromCart).mockReturnValue(
      new Promise<SubmitResult>((resolve) => {
        resolveSubmit = resolve;
      })
    );

    const { result } = renderHook(
      () => useCheckoutPage({ authLoading: false, isAuthenticated: false }),
      { wrapper: wrapper() }
    );

    let finalize: Promise<void>;
    act(() => {
      finalize = result.current.onFinalizeCheckout();
    });
    await waitFor(() => expect(result.current.loading).toBe(true));

    act(() => {
      result.current.onRemoveItem(10);
    });
    expect(removeCartItem).not.toHaveBeenCalled();

    await act(async () => {
      resolveSubmit({
        order: { id: 1, status: "submitted", total_amount: 10000, items: [{ id: 1 }] },
        payment: { id: 1, method: "bank_transfer", status: "pending", amount: 10000, currency: "ARS" },
      });
      await finalize;
    });
  });
});
