import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BankTransferStatusPage } from "./BankTransferStatusPage";
import { fetchPublicBankTransferStatus } from "../services/payments-api";
import type { PublicBankTransferStatus } from "../types";

vi.mock("../services/payments-api", () => ({
  fetchPublicBankTransferStatus: vi.fn()
}));

const INSTRUCTIONS = {
  alias: "patitas.bigotes.real",
  cbu: "0110599520000012345678",
  bank_name: "Banco Nacion",
  holder: "Martin Capisano",
  tax_id: "20-35123456-7",
  reference: "ORDER-12-PAY-34",
  amount: 25990,
  currency: "ARS",
  whatsapp_number: "5493511234567",
  whatsapp_url: "https://wa.me/5493511234567?text=Referencia%3A%20ORDER-12-PAY-34"
};

function payable(overrides: Partial<PublicBankTransferStatus> = {}): PublicBankTransferStatus {
  return {
    order_id: 12,
    order_status: "submitted",
    order_total: 25990,
    currency: "ARS",
    items: [
      {
        product_name: "Balanceado Adulto Premium",
        variant_label: "3 kg/-",
        quantity: 1,
        line_total: 25990
      }
    ],
    payment_id: 34,
    payment_status: "pending",
    can_pay: true,
    instructions: INSTRUCTIONS,
    ...overrides
  };
}

function renderPage(search: string) {
  return render(
    <MemoryRouter initialEntries={[`/transferencia${search}`]}>
      <BankTransferStatusPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("BankTransferStatusPage", () => {
  it("shows the instructions to a guest carrying the token", async () => {
    vi.mocked(fetchPublicBankTransferStatus).mockResolvedValue(payable());

    renderPage("?token=tok-invitado");

    await waitFor(() => expect(screen.getByText("patitas.bigotes.real")).toBeInTheDocument());
    expect(screen.getByText("0110599520000012345678")).toBeInTheDocument();
    // The reference shows twice on purpose: as a copyable field and inside the
    // sentence explaining what it is for.
    expect(screen.getAllByText("ORDER-12-PAY-34").length).toBeGreaterThan(0);
    // Scoped: the amount also appears in the purchase detail above.
    const amountBlock = document.querySelector(".transfer-amount-block") as HTMLElement;
    expect(within(amountBlock).getByText("$ 259,90")).toBeInTheDocument();
    expect(fetchPublicBankTransferStatus).toHaveBeenCalledWith({
      publicStatusToken: "tok-invitado"
    });
  });

  it("says what the customer bought, not just how much to pay", async () => {
    // A guest has no order history: with two pending transfers, the amount
    // alone does not tell them which one this screen is asking for.
    vi.mocked(fetchPublicBankTransferStatus).mockResolvedValue(payable());

    renderPage("?token=tok-invitado");

    await waitFor(() =>
      expect(screen.getByText("Balanceado Adulto Premium")).toBeInTheDocument()
    );
    expect(screen.getByText("3 kg/- x 1")).toBeInTheDocument();
  });

  it("keeps showing what was bought after the payment is settled", async () => {
    // The bank data goes away; the purchase it paid for does not.
    vi.mocked(fetchPublicBankTransferStatus).mockResolvedValue(
      payable({
        order_status: "paid",
        payment_status: "paid",
        can_pay: false,
        instructions: null
      })
    );

    renderPage("?token=tok-pagado");

    await waitFor(() =>
      expect(screen.getByText("Balanceado Adulto Premium")).toBeInTheDocument()
    );
    expect(screen.queryByText("patitas.bigotes.real")).not.toBeInTheDocument();
  });

  it("shows the state instead of the data once the payment is settled", async () => {
    // Repeating the alias here would be inviting a second transfer nobody can
    // match to anything.
    vi.mocked(fetchPublicBankTransferStatus).mockResolvedValue(
      payable({
        order_status: "paid",
        payment_status: "paid",
        can_pay: false,
        instructions: null
      })
    );

    renderPage("?token=tok-pagado");

    await waitFor(() => expect(screen.getByText(/ya fue confirmado/i)).toBeInTheDocument());
    expect(screen.queryByText("patitas.bigotes.real")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copiar CBU" })).not.toBeInTheDocument();
  });

  it("explains a cancelled order without offering the data", async () => {
    vi.mocked(fetchPublicBankTransferStatus).mockResolvedValue(
      payable({
        order_status: "cancelled",
        payment_status: "cancelled",
        can_pay: false,
        instructions: null
      })
    );

    renderPage("?token=tok-cancelado");

    await waitFor(() => expect(screen.getByText(/fue cancelada/i)).toBeInTheDocument());
    expect(screen.queryByText("patitas.bigotes.real")).not.toBeInTheDocument();
  });

  it("refuses to render half the data", async () => {
    const partial = { ...INSTRUCTIONS };
    delete (partial as Partial<typeof INSTRUCTIONS>).cbu;
    vi.mocked(fetchPublicBankTransferStatus).mockResolvedValue(
      payable({ instructions: partial })
    );

    renderPage("?token=tok-parcial");

    await waitFor(() =>
      expect(screen.queryByText("patitas.bigotes.real")).not.toBeInTheDocument()
    );
  });

  it("asks for the link to be checked when the token is missing", async () => {
    renderPage("");

    await waitFor(() => expect(screen.getByText(/no trae el codigo/i)).toBeInTheDocument());
    expect(fetchPublicBankTransferStatus).not.toHaveBeenCalled();
  });

  it("reports a lookup that fails instead of showing an empty screen", async () => {
    vi.mocked(fetchPublicBankTransferStatus).mockRejectedValue(new Error("boom"));

    renderPage("?token=tok-roto");

    await waitFor(() => expect(document.querySelector(".error")).toBeTruthy());
    expect(screen.queryByText("patitas.bigotes.real")).not.toBeInTheDocument();
  });
});
