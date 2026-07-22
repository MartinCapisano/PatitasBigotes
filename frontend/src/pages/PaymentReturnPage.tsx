import { Link } from "react-router-dom";
import { type PaymentReturnVariant, usePaymentReturnStatus } from "../features/checkout";
import { formatMoney } from "../lib/money";
import type { PublicOrderBlockingReason } from "../types";

const CONTENT: Record<PaymentReturnVariant, { title: string; subtitle: string }> = {
  success: {
    title: "Pago aprobado",
    subtitle: "MercadoPago informo que tu pago fue aprobado. Si el estado tarda en actualizar, refresca en unos segundos."
  },
  failure: {
    title: "Pago rechazado",
    subtitle: "MercadoPago informo que el pago fue rechazado o no pudo completarse. Podes reintentar desde tu checkout."
  },
  pending: {
    title: "Pago pendiente",
    subtitle: "MercadoPago dejo el pago en estado pendiente. Te avisaremos cuando cambie el estado."
  }
};

const BLOCKING_REASON_MESSAGE: Record<PublicOrderBlockingReason, string> = {
  order_paid: "La orden ya fue abonada.",
  order_cancelled: "La orden fue cancelada y ya no admite pagos.",
  payment_pending: "El pago sigue pendiente. Reconsulta el estado en unos segundos.",
  payment_not_retryable: "Este pago ya no puede reintentarse desde aqui.",
  stock_reservation_expired: "La reserva de stock vencio. Ya no podemos reintentar este pago.",
  checkout_unavailable: "No pudimos recuperar el enlace de Mercado Pago para este intento.",
};

export function PaymentReturnPage({ variant }: { variant: PaymentReturnVariant }) {
  const {
    location,
    status,
    snapshot,
    loading,
    retrying,
    hasActiveRetryCheckout,
    error,
    retryError,
    loadStatus,
    onContinuePayment,
    onRetryPayment
  } = usePaymentReturnStatus();
  const { title, subtitle } = CONTENT[variant];
  const blockingMessage = snapshot?.blocking_reason
    ? BLOCKING_REASON_MESSAGE[snapshot.blocking_reason]
    : null;

  return (
    <section>
      <h1 className="page-title">{title}</h1>
      <p className="page-subtitle">{subtitle}</p>
      {loading && <p className="muted">Consultando estado de pago...</p>}
      {error && <p className="error">{error}</p>}
      {snapshot ? (
        <div className="card">
          <p><strong>Estado del pago:</strong> {snapshot.payment.status}</p>
          <p className="muted">Estado de orden: {snapshot.order.status}</p>
          <p><strong>Total:</strong> {formatMoney(snapshot.order.total_amount, snapshot.order.currency)}</p>
          {snapshot.order.items.length > 0 && (
            <div>
              <p><strong>Detalle:</strong></p>
              {snapshot.order.items.map((item, index) => (
                <p className="muted" key={`${item.product_name ?? "producto"}-${item.variant_label}-${index}`}>
                  {item.quantity} x {item.product_name ?? "Producto"} ({item.variant_label}) - {formatMoney(item.line_total, snapshot.order.currency)}
                </p>
              ))}
            </div>
          )}
          {blockingMessage && <p className="muted">{blockingMessage}</p>}
        </div>
      ) : status && (
        <div className="card">
          <p><strong>Estado del pago:</strong> {status.status}</p>
          <p className="muted">Estado de orden: {status.order_status ?? "-"}</p>
        </div>
      )}
      {retryError && <p className="error">{retryError}</p>}
      <div className="checkout-actions">
        <button className="btn btn-small btn-ghost" type="button" onClick={() => void loadStatus()} disabled={loading}>
          Reconsultar estado
        </button>
        {(hasActiveRetryCheckout || snapshot?.flags.can_continue_payment) && (
          <button className="btn btn-small" type="button" onClick={onContinuePayment} disabled={loading || retrying}>
            Continuar pago
          </button>
        )}
        {snapshot?.flags.can_retry_payment && !hasActiveRetryCheckout && (
          <button className="btn btn-small" type="button" onClick={() => void onRetryPayment()} disabled={loading || retrying}>
            {retrying ? "Redirigiendo..." : "Reintentar pago"}
          </button>
        )}
        {!snapshot && location.search && (
          <Link className="btn btn-small" to="/checkout">
            Volver al checkout
          </Link>
        )}
        <Link className="btn btn-small btn-ghost" to="/home">
          Ir a tienda
        </Link>
      </div>
    </section>
  );
}
