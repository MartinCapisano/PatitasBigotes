import type { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { useLoginPage } from "./useLoginPage";

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: vi.fn(actual.useNavigate) };
});

function wrapper(initialState?: Record<string, unknown>) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={[{ pathname: "/login", state: initialState }]}>
        {children}
      </MemoryRouter>
    );
  };
}

function submitEvent() {
  return { preventDefault: () => undefined } as unknown as React.FormEvent;
}

describe("useLoginPage", () => {
  it("navigates to /admin when login resolves as admin", async () => {
    const navigateSpy = vi.fn();
    vi.mocked(useNavigate).mockReturnValue(navigateSpy);
    const login = vi.fn().mockResolvedValue(true);

    const { result } = renderHook(() => useLoginPage(login), { wrapper: wrapper() });

    act(() => {
      result.current.setEmail("admin@example.com");
      result.current.setPassword("Secret!123");
    });
    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    expect(login).toHaveBeenCalledWith("admin@example.com", "Secret!123");
    expect(navigateSpy).toHaveBeenCalledWith("/admin");
  });

  it("navigates to /profile when login resolves as a regular user", async () => {
    const navigateSpy = vi.fn();
    vi.mocked(useNavigate).mockReturnValue(navigateSpy);
    const login = vi.fn().mockResolvedValue(false);

    const { result } = renderHook(() => useLoginPage(login), { wrapper: wrapper() });

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    expect(navigateSpy).toHaveBeenCalledWith("/profile");
  });

  it("redirects back to /checkout when arriving from the checkout flow", async () => {
    const navigateSpy = vi.fn();
    vi.mocked(useNavigate).mockReturnValue(navigateSpy);
    const login = vi.fn().mockResolvedValue(false);

    const { result } = renderHook(() => useLoginPage(login), {
      wrapper: wrapper({ from: "/checkout" }),
    });

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    expect(navigateSpy).toHaveBeenCalledWith("/checkout", { replace: true });
  });

  it("prefills the email and shows an info message for registered_account_checkout", () => {
    const { result } = renderHook(
      () => useLoginPage(vi.fn()),
      {
        wrapper: wrapper({
          checkoutEmail: "shopper@example.com",
          reason: "registered_account_checkout",
        }),
      },
    );

    expect(result.current.email).toBe("shopper@example.com");
    expect(result.current.infoMessage).toBe(
      "Ese email ya tiene cuenta. Inicia sesion para continuar con tu carrito."
    );
  });

  it("shows a generic error message when login fails and does not navigate", async () => {
    const navigateSpy = vi.fn();
    vi.mocked(useNavigate).mockReturnValue(navigateSpy);
    const login = vi.fn().mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() => useLoginPage(login), { wrapper: wrapper() });

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    await waitFor(() => {
      expect(result.current.error).toBe("No se pudo iniciar sesion.");
    });
    expect(result.current.loading).toBe(false);
    expect(navigateSpy).not.toHaveBeenCalled();
  });
});
