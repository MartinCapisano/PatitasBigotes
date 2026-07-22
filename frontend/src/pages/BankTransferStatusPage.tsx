import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BankTransferInstructions } from "../features/checkout";
import { readBankTransferInstructions } from "../lib/bank-transfer";
import { formatMoney } from "../lib/money";
import { toUserMessage } from "../services/http-errors";
import { fetchPublicBankTransferStatus } from "../services/payments-api";
import type { PublicBankTransferStatus } from "../types";

/**
 * The way back to a transfer for someone with no account.
 *
 * A guest who closed the tab has no other route to their alias, CBU and
 * reference; the token in the URL is the whole credential.
 */
const CLOSED_REASON: Record<string, string> = {
  paid: "Tu pago ya fue confirmado. No hace falta que transfieras de nuevo.",
  cancelled: "Esta orden fue cancelada, asi que ya no corresponde transferir."
};

export function BankTransferStatusPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<PublicBankTransferStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!token) {
        setError("El enlace no trae el codigo de tu pago. Reviselo o escribinos.");
        setLoading(false);
        return;
      }
      setLoading(true);
      setError("");
      try {
        const next = await fetchPublicBankTransferStatus({ publicStatusToken: token });
        if (!cancelled) setStatus(next);
      } catch (apiError: unknown) {
        if (!cancelled) setError(toUserMessage(apiError, "checkout"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const instructions = status?.can_pay
    ? readBankTransferInstructions(status.instructions)
    : null;

  return (
    <section>
      <h1 className="page-title">Datos para tu transferencia</h1>
      {loading && <p className="muted">Buscando tu pago...</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && status && status.items.length > 0 && (
        <div className="card">
          <h2>Tu compra</h2>
          <p className="muted">
            Orden #{status.order_id} - {status.order_status}
          </p>
          {status.items.map((item, index) => (
            <div
              className="checkout-row"
              key={`${item.product_name ?? "producto"}-${item.variant_label}-${index}`}
            >
              <div className="checkout-row-main">
                <strong>{item.product_name ?? "Producto"}</strong>
                <p className="muted">
                  {item.variant_label} x {item.quantity}
                </p>
              </div>
              <div className="checkout-row-side">{formatMoney(item.line_total, status.currency)}</div>
            </div>
          ))}
          <p className="checkout-total">{formatMoney(status.order_total, status.currency)}</p>
        </div>
      )}

      {!loading && !error && status && instructions && (
        <BankTransferInstructions orderId={status.order_id} instructions={instructions} />
      )}

      {!loading && !error && status && !instructions && (
        <div className="card">
          <p className="muted">Estado del pago: {status.payment_status}</p>
          <p>
            {CLOSED_REASON[status.order_status] ??
              CLOSED_REASON[status.payment_status] ??
              "Este pago ya no admite una transferencia. Escribinos si necesitas ayuda."}
          </p>
          <div className="checkout-actions">
            <Link className="btn btn-small" to="/home">
              Ir a la tienda
            </Link>
          </div>
        </div>
      )}
    </section>
  );
}
