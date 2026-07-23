import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VerifyEmailPage } from "./VerifyEmailPage";
import { EMAIL_COOLDOWN_SECONDS, savePendingVerificationEmail } from "../features/auth/verification-storage";

const { requestEmailVerification, confirmEmailVerification } = vi.hoisted(() => ({
  requestEmailVerification: vi.fn(),
  confirmEmailVerification: vi.fn()
}));
vi.mock("../services/auth-api", () => ({ requestEmailVerification, confirmEmailVerification }));
vi.mock("../auth/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: false }) }));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/verify-email"]}>
      <VerifyEmailPage />
    </MemoryRouter>
  );
}

describe("VerifyEmailPage", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    savePendingVerificationEmail("ana@example.com");
    requestEmailVerification.mockReset();
    requestEmailVerification.mockResolvedValue(undefined);
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("counts down on the resend button and re-enables it on its own", async () => {
    // El guard de `loading` solo cubria el doble click durante la request:
    // apenas terminaba, el segundo click traia un 429 crudo en ingles.
    renderPage();
    const button = screen.getByRole("button", { name: "Reenviar email" });

    await act(async () => {
      button.click();
    });

    const cooling = screen.getByRole("button", { name: `Reenviar en ${EMAIL_COOLDOWN_SECONDS}s...` });
    expect(cooling).toBeDisabled();

    await act(async () => {
      vi.advanceTimersByTime(EMAIL_COOLDOWN_SECONDS * 1000);
    });

    expect(screen.getByRole("button", { name: "Reenviar email" })).toBeEnabled();
    expect(requestEmailVerification).toHaveBeenCalledTimes(1);
  });

  it("keeps counting after a page reload", async () => {
    const { unmount } = renderPage();
    await act(async () => {
      screen.getByRole("button", { name: "Reenviar email" }).click();
    });
    unmount();

    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    renderPage();

    expect(
      screen.getByRole("button", { name: `Reenviar en ${EMAIL_COOLDOWN_SECONDS - 10}s...` })
    ).toBeDisabled();
  });
});
