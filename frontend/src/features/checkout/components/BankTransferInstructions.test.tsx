import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BankTransferInstructions, TRANSFER_DEADLINE_HOURS } from "./BankTransferInstructions";
import { buildBankTransferStatusUrl } from "../../../lib/bank-transfer";
import type { BankTransferInstructions as Instructions } from "../../../types";

const INSTRUCTIONS: Instructions = {
  alias: "patitas.bigotes.real",
  cbu: "0110599520000012345678",
  bank_name: "Banco Nacion",
  holder: "Martin Capisano",
  tax_id: "20-35123456-7",
  reference: "ORDER-12-PAY-34",
  amount: 250000,
  currency: "ARS",
  whatsapp_number: "5493511234567",
  whatsapp_url:
    "https://wa.me/5493511234567?text=Hola%21%20Te%20env%C3%ADo%20el%20comprobante%20de%20mi%20transferencia.%20Referencia%3A%20ORDER-12-PAY-34"
};

function renderInstructions(
  overrides: Partial<Instructions> = {},
  publicStatusToken: string | null = null
) {
  return render(
    <MemoryRouter>
      <BankTransferInstructions
        orderId={12}
        instructions={{ ...INSTRUCTIONS, ...overrides }}
        publicStatusToken={publicStatusToken}
      />
    </MemoryRouter>
  );
}

function stubClipboard(writeText: () => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn(writeText) },
    configurable: true,
    writable: true
  });
  return navigator.clipboard.writeText as ReturnType<typeof vi.fn>;
}

describe("BankTransferInstructions", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it("shows every value the customer needs to transfer", () => {
    renderInstructions();

    expect(screen.getByText("patitas.bigotes.real")).toBeInTheDocument();
    expect(screen.getByText("0110599520000012345678")).toBeInTheDocument();
    expect(screen.getByText("Banco Nacion")).toBeInTheDocument();
    expect(screen.getByText("Martin Capisano")).toBeInTheDocument();
    expect(screen.getByText("20-35123456-7")).toBeInTheDocument();
  });

  it("shows the exact amount the customer has to transfer", () => {
    // This is the number they type into their banking app: a rounded $ 260
    // would buy a payment that does not match the order total.
    renderInstructions({ amount: 25990 });

    expect(screen.getByText("$ 259,90")).toBeInTheDocument();
    expect(screen.queryByText("$ 260")).not.toBeInTheDocument();
  });

  it("states the deadline the customer is being promised", () => {
    renderInstructions();

    expect(
      screen.getByText(
        `Tenés ${TRANSFER_DEADLINE_HOURS} hs para transferir, sino la orden se cancela.`
      )
    ).toBeInTheDocument();
  });

  it("keeps the promised deadline under the stock reservation window", () => {
    // The reservation is what actually cancels the order, at 42 h. Promising
    // more than that would mean cancelling before the deadline we gave.
    expect(TRANSFER_DEADLINE_HOURS).toBeLessThan(42);
  });

  it("links to WhatsApp with the reference already in the message", () => {
    renderInstructions();

    const link = screen.getByRole("link", { name: /comprobante por WhatsApp/i });
    expect(link).toHaveAttribute("href", INSTRUCTIONS.whatsapp_url);
    expect(decodeURIComponent(link.getAttribute("href") ?? "")).toContain("ORDER-12-PAY-34");
  });

  it("opens WhatsApp in a new tab without handing it the opener", () => {
    renderInstructions();

    const link = screen.getByRole("link", { name: /comprobante por WhatsApp/i });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("shows the order it belongs to", () => {
    renderInstructions();

    expect(screen.getByText(/orden #12/i)).toBeInTheDocument();
  });

  it("copies the alias and confirms it visibly", async () => {
    const writeText = stubClipboard(() => Promise.resolve());
    renderInstructions();

    fireEvent.click(screen.getByRole("button", { name: "Copiar Alias" }));

    expect(writeText).toHaveBeenCalledWith("patitas.bigotes.real");
    await waitFor(() => expect(screen.getByText("Copiado")).toBeInTheDocument());
  });

  it("copies the CBU", async () => {
    const writeText = stubClipboard(() => Promise.resolve());
    renderInstructions();

    fireEvent.click(screen.getByRole("button", { name: "Copiar CBU" }));

    expect(writeText).toHaveBeenCalledWith("0110599520000012345678");
  });

  it("copies the reference, which is what ties the money to the order", async () => {
    const writeText = stubClipboard(() => Promise.resolve());
    renderInstructions();

    fireEvent.click(screen.getByRole("button", { name: "Copiar Referencia" }));

    expect(writeText).toHaveBeenCalledWith("ORDER-12-PAY-34");
  });

  it("confirms only the field that was copied", async () => {
    stubClipboard(() => Promise.resolve());
    renderInstructions();

    fireEvent.click(screen.getByRole("button", { name: "Copiar CBU" }));

    await waitFor(() => expect(screen.getAllByText("Copiado")).toHaveLength(1));
  });

  it("offers a link back to these instructions when there is a token", () => {
    // A guest has no account: without this link, closing the tab loses the
    // alias, the CBU and the reference for good.
    renderInstructions({}, "tok-invitado-42");

    expect(screen.getByText(/guardate este enlace/i)).toBeInTheDocument();
    expect(
      screen.getByText(buildBankTransferStatusUrl("tok-invitado-42", window.location.origin))
    ).toBeInTheDocument();
  });

  it("makes that link copyable too", async () => {
    const writeText = stubClipboard(() => Promise.resolve());
    renderInstructions({}, "tok-invitado-42");

    fireEvent.click(screen.getByRole("button", { name: "Copiar Enlace" }));

    expect(writeText).toHaveBeenCalledWith(
      buildBankTransferStatusUrl("tok-invitado-42", window.location.origin)
    );
  });

  it("does not offer the link when there is no token", () => {
    renderInstructions();

    expect(screen.queryByText(/guardate este enlace/i)).not.toBeInTheDocument();
  });

  it("escapes the token so it survives the URL", () => {
    expect(buildBankTransferStatusUrl("a b/c?d", "https://tienda.test")).toBe(
      "https://tienda.test/transferencia?token=a%20b%2Fc%3Fd"
    );
  });

  it("tells the customer to copy by hand when the clipboard refuses", async () => {
    // Insecure contexts and denied permissions reject: staying silent would let
    // someone paste a stale CBU into their banking app believing it worked.
    stubClipboard(() => Promise.reject(new Error("denied")));
    renderInstructions();

    fireEvent.click(screen.getByRole("button", { name: "Copiar CBU" }));

    await waitFor(() =>
      expect(screen.getByText("No se pudo copiar, copialo a mano")).toBeInTheDocument()
    );
    expect(screen.queryByText("Copiado")).not.toBeInTheDocument();
  });
});
