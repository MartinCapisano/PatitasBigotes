import type { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { usePaymentReturnStatus } from "./usePaymentReturnStatus";
import {
  getMercadoPagoCheckoutUrl,
  redirectToMercadoPago,
} from "../../../services/checkout-api";
import {
  fetchPublicOrderSnapshotByPaymentToken,
  retryGuestMercadoPago,
} from "../../../services/payments-api";
import type { MyPayment, PublicOrderSnapshot } from "../../../types";

vi.mock("../../../services/checkout-api", () => ({
  getMercadoPagoCheckoutUrl: vi.fn(),
  redirectToMercadoPago: vi.fn(),
}));

vi.mock("../../../services/payments-api", () => ({
  fetchPublicOrderSnapshotByPaymentToken: vi.fn(),
  retryGuestMercadoPago: vi.fn(),
}));

vi.mock("../../../services/idempotency", () => ({
  buildIdempotencyKey: vi.fn(() => "idem-key-1"),
}));

const TOKEN = "tok-123";

function wrapper(search = `?public_status_token=${TOKEN}`) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <MemoryRouter initialEntries={[`/payment-return${search}`]}>{children}</MemoryRouter>;
  };
}

function makeSnapshot(overrides: Partial<PublicOrderSnapshot> = {}): PublicOrderSnapshot {
  return {
    order: { status: "submitted", total_amount: 10000, currency: "ARS", items: [] },
    payment: {
      method: "mercadopago",
      status: "pending",
      amount: 10000,
      currency: "ARS",
      checkout_url: null,
    },
    flags: {
      can_continue_payment: false,
      can_retry_payment: false,
      is_order_open: true,
      is_payment_terminal: false,
    },
    blocking_reason: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("usePaymentReturnStatus", () => {
  it("loads the order snapshot from the token in the URL on mount", async () => {
    vi.mocked(fetchPublicOrderSnapshotByPaymentToken).mockResolvedValue(makeSnapshot());

    const { result } = renderHook(() => usePaymentReturnStatus(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.snapshot).not.toBeNull());
    expect(fetchPublicOrderSnapshotByPaymentToken).toHaveBeenCalledWith({
      publicStatusToken: TOKEN,
    });
    expect(result.current.status?.status).toBe("pending");
    expect(result.current.error).toBe("");
  });

  it("sets an error and skips the request when the token is missing from the URL", async () => {
    const { result } = renderHook(() => usePaymentReturnStatus(), {
      wrapper: wrapper("?"),
    });

    await waitFor(() => expect(result.current.error).not.toBe(""));
    expect(fetchPublicOrderSnapshotByPaymentToken).not.toHaveBeenCalled();
    expect(result.current.snapshot).toBeNull();
  });

  it("clears snapshot and surfaces an error message when the load request fails", async () => {
    vi.mocked(fetchPublicOrderSnapshotByPaymentToken).mockRejectedValue({
      response: { status: 500, data: {} },
    });

    const { result } = renderHook(() => usePaymentReturnStatus(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.error).not.toBe(""));
    expect(result.current.snapshot).toBeNull();
    expect(result.current.status).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it("blocks retry when the snapshot flag can_retry_payment is false", async () => {
    vi.mocked(fetchPublicOrderSnapshotByPaymentToken).mockResolvedValue(
      makeSnapshot({
        flags: {
          can_continue_payment: false,
          can_retry_payment: false,
          is_order_open: true,
          is_payment_terminal: false,
        },
      })
    );

    const { result } = renderHook(() => usePaymentReturnStatus(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.snapshot).not.toBeNull());

    await act(async () => {
      await result.current.onRetryPayment();
    });

    expect(retryGuestMercadoPago).not.toHaveBeenCalled();
    expect(result.current.retryError).not.toBe("");
  });

  it("retries the guest payment and redirects to the fresh MercadoPago checkout URL", async () => {
    vi.mocked(fetchPublicOrderSnapshotByPaymentToken).mockResolvedValue(
      makeSnapshot({
        flags: {
          can_continue_payment: false,
          can_retry_payment: true,
          is_order_open: true,
          is_payment_terminal: false,
        },
      })
    );
    vi.mocked(retryGuestMercadoPago).mockResolvedValue({ id: 5 } as MyPayment);
    vi.mocked(getMercadoPagoCheckoutUrl).mockReturnValue("https://mercadopago.com/checkout/new");

    const { result } = renderHook(() => usePaymentReturnStatus(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.snapshot).not.toBeNull());

    await act(async () => {
      await result.current.onRetryPayment();
    });

    expect(retryGuestMercadoPago).toHaveBeenCalledWith(TOKEN, "idem-key-1");
    expect(redirectToMercadoPago).toHaveBeenCalledWith("https://mercadopago.com/checkout/new");
    expect(result.current.retryError).toBe("");
  });

  it("shows a retry error and reloads the snapshot when retry returns no checkout URL", async () => {
    vi.mocked(fetchPublicOrderSnapshotByPaymentToken).mockResolvedValue(
      makeSnapshot({
        flags: {
          can_continue_payment: false,
          can_retry_payment: true,
          is_order_open: true,
          is_payment_terminal: false,
        },
      })
    );
    vi.mocked(retryGuestMercadoPago).mockResolvedValue({ id: 5 } as MyPayment);
    vi.mocked(getMercadoPagoCheckoutUrl).mockReturnValue(null);

    const { result } = renderHook(() => usePaymentReturnStatus(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.snapshot).not.toBeNull());
    vi.mocked(fetchPublicOrderSnapshotByPaymentToken).mockClear();

    await act(async () => {
      await result.current.onRetryPayment();
    });

    expect(redirectToMercadoPago).not.toHaveBeenCalled();
    expect(result.current.retryError).not.toBe("");
    // reload triggered to refresh the terminal state after the failed retry
    expect(fetchPublicOrderSnapshotByPaymentToken).toHaveBeenCalledTimes(1);
  });

  it("continues an existing payment using the snapshot checkout URL", async () => {
    vi.mocked(fetchPublicOrderSnapshotByPaymentToken).mockResolvedValue(
      makeSnapshot({
        payment: {
          method: "mercadopago",
          status: "pending",
          amount: 10000,
          currency: "ARS",
          checkout_url: "https://mercadopago.com/checkout/continue",
        },
        flags: {
          can_continue_payment: true,
          can_retry_payment: false,
          is_order_open: true,
          is_payment_terminal: false,
        },
      })
    );

    const { result } = renderHook(() => usePaymentReturnStatus(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.snapshot).not.toBeNull());

    act(() => {
      result.current.onContinuePayment();
    });

    expect(redirectToMercadoPago).toHaveBeenCalledWith(
      "https://mercadopago.com/checkout/continue"
    );
    expect(result.current.retryError).toBe("");
  });

  it("shows an error when continuing a payment that has no checkout URL", async () => {
    vi.mocked(fetchPublicOrderSnapshotByPaymentToken).mockResolvedValue(
      makeSnapshot({
        flags: {
          can_continue_payment: true,
          can_retry_payment: false,
          is_order_open: true,
          is_payment_terminal: false,
        },
      })
    );

    const { result } = renderHook(() => usePaymentReturnStatus(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.snapshot).not.toBeNull());

    act(() => {
      result.current.onContinuePayment();
    });

    expect(redirectToMercadoPago).not.toHaveBeenCalled();
    expect(result.current.retryError).not.toBe("");
  });
});
