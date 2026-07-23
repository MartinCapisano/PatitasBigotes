import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useForgotPasswordPage } from "./useForgotPasswordPage";
import { EMAIL_COOLDOWN_SECONDS } from "../verification-storage";

const { requestPasswordReset } = vi.hoisted(() => ({ requestPasswordReset: vi.fn() }));
vi.mock("../../../services/auth-api", () => ({ requestPasswordReset }));

function submitEvent() {
  return { preventDefault: () => undefined } as unknown as React.FormEvent;
}

describe("useForgotPasswordPage", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    requestPasswordReset.mockReset();
    requestPasswordReset.mockResolvedValue(undefined);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows a countdown instead of an error when the form is sent again too soon", async () => {
    // Volver a mandar este formulario ES el reenvio, y el backend lo throttlea
    // igual que al de verificacion. Antes el segundo envio traia un 429 crudo
    // en ingles.
    const { result } = renderHook(() => useForgotPasswordPage());

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });
    expect(result.current.resendCooldownSeconds).toBe(EMAIL_COOLDOWN_SECONDS);
    expect(result.current.error).toBe("");

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    expect(requestPasswordReset).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBe("");
  });

  it("accepts a new send once the window is over", async () => {
    const { result } = renderHook(() => useForgotPasswordPage());
    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    act(() => {
      vi.advanceTimersByTime(EMAIL_COOLDOWN_SECONDS * 1000);
    });
    expect(result.current.resendCooldownSeconds).toBe(0);

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    expect(requestPasswordReset).toHaveBeenCalledTimes(2);
  });

  it("does not start the cooldown when the send failed", async () => {
    // Si no salio ningun mail, el usuario tiene que poder reintentar en el acto.
    requestPasswordReset.mockRejectedValue(new Error("network"));
    const { result } = renderHook(() => useForgotPasswordPage());

    await act(async () => {
      await result.current.onSubmit(submitEvent());
    });

    expect(result.current.resendCooldownSeconds).toBe(0);
    expect(result.current.error).not.toBe("");
  });
});
