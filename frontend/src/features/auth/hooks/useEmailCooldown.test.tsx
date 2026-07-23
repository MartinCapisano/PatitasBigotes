import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useEmailCooldown } from "./useEmailCooldown";
import { EMAIL_COOLDOWN_SECONDS, startEmailCooldown } from "../verification-storage";

describe("useEmailCooldown", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("blocks for the full window after a send", () => {
    const { result } = renderHook(() => useEmailCooldown("verification"));

    act(() => result.current.start());

    expect(result.current.active).toBe(true);
    expect(result.current.remainingSeconds).toBe(EMAIL_COOLDOWN_SECONDS);
  });

  it("survives a page reload", () => {
    // El punto entero de persistirlo: en memoria, un F5 reseteaba el contador y
    // el siguiente click volvia a traer el 429 en ingles.
    const { result, unmount } = renderHook(() => useEmailCooldown("verification"));
    act(() => result.current.start());
    unmount();

    vi.advanceTimersByTime(5000);
    const remounted = renderHook(() => useEmailCooldown("verification"));

    expect(remounted.result.current.active).toBe(true);
    expect(remounted.result.current.remainingSeconds).toBe(EMAIL_COOLDOWN_SECONDS - 5);
  });

  it("counts down and releases the button on its own", () => {
    const { result } = renderHook(() => useEmailCooldown("verification"));
    act(() => result.current.start());

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.remainingSeconds).toBe(EMAIL_COOLDOWN_SECONDS - 1);

    act(() => {
      vi.advanceTimersByTime(EMAIL_COOLDOWN_SECONDS * 1000);
    });
    expect(result.current.active).toBe(false);
    expect(result.current.remainingSeconds).toBe(0);
  });

  it("keeps the two sends on separate counters", () => {
    // En el backend son contadores distintos: pedir el reset no puede trabar el
    // reenvio de verificacion.
    const verification = renderHook(() => useEmailCooldown("verification"));
    const passwordReset = renderHook(() => useEmailCooldown("password-reset"));

    act(() => verification.result.current.start());

    expect(verification.result.current.active).toBe(true);
    expect(passwordReset.result.current.active).toBe(false);
  });

  it("does not stay locked when the clock jumps backwards", () => {
    startEmailCooldown("verification", Date.now() + 60_000);

    const { result } = renderHook(() => useEmailCooldown("verification"));

    expect(result.current.active).toBe(false);
  });

  it("ignores a corrupted stored value", () => {
    window.sessionStorage.setItem("pb_email_cooldown_verification", "no-es-un-numero");

    const { result } = renderHook(() => useEmailCooldown("verification"));

    expect(result.current.active).toBe(false);
  });
});
