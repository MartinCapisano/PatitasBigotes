import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import {
  BankTransferInstructions,
  formatArs,
  getAvailablePaymentMethods,
  useCheckoutPage
} from "../features/checkout";
import type { CheckoutPaymentMethod } from "../services/checkout-api";

export function CheckoutPage() {
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const checkout = useCheckoutPage({ authLoading, isAuthenticated });
  const paymentMethods = getAvailablePaymentMethods();

  return (
    <section>
      <h1 className="page-title">Finalizar compra</h1>
      {authLoading && <p className="muted">Verificando sesion...</p>}
      <p className="page-subtitle">
        {checkout.bankTransfer
          ? "Tu orden quedo registrada. Falta un paso: hacer la transferencia."
          : authLoading
          ? "Estamos validando tu sesion antes de continuar."
          : isAuthenticated
          ? "Checkout de cuenta: se crea orden del usuario y se envia a submitted."
          : "Checkout invitado: completa tus datos para enviar la orden."}
      </p>

      {checkout.bankTransfer ? (
        <BankTransferInstructions
          orderId={checkout.bankTransfer.orderId}
          instructions={checkout.bankTransfer.instructions}
          publicStatusToken={checkout.bankTransfer.publicStatusToken}
        />
      ) : checkout.items.length === 0 ? (
        <div className="card">
          <p>Tu carrito esta vacio.</p>
          <Link className="btn btn-small" to="/home">
            Ir a tienda
          </Link>
        </div>
      ) : (
        <div className="checkout-grid">
          <div className="card">
            {checkout.items.map((item) => (
              <div key={`${item.product_id}-${item.variant_id}`} className="checkout-row">
                <div className="checkout-row-main">
                  <strong>{item.product_name}</strong>
                  <p className="muted">Opcion: {item.option_label}</p>
                  <p className="muted">Precio unitario: {formatArs(item.unit_price)}</p>
                </div>
                <div className="checkout-row-side">
                  <div className="checkout-qty-controls">
                    <button
                      className="btn btn-small btn-ghost"
                      type="button"
                      onClick={() => checkout.onDecrementItem(item.variant_id, item.quantity)}
                      disabled={checkout.loading || item.quantity <= 1}
                      aria-label={`Disminuir cantidad de ${item.product_name}`}
                    >
                      -
                    </button>
                    <span className="checkout-qty-value">{item.quantity}</span>
                    <button
                      className="btn btn-small btn-ghost"
                      type="button"
                      onClick={() => checkout.onIncrementItem(item.variant_id, item.quantity)}
                      disabled={checkout.loading || item.quantity >= 10}
                      aria-label={`Aumentar cantidad de ${item.product_name}`}
                    >
                      +
                    </button>
                  </div>
                  <p className="muted">Subtotal linea: {formatArs(item.unit_price * item.quantity)}</p>
                  <button
                    className="btn btn-small btn-ghost"
                    type="button"
                    onClick={() => checkout.onRemoveItem(item.variant_id)}
                    disabled={checkout.loading}
                  >
                    Eliminar
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="card">
            <h2>Total</h2>
            <p className="checkout-total">{formatArs(checkout.total)}</p>
            <label>
              Metodo de pago
              <select className="input" value={checkout.paymentMethod} onChange={(event) => checkout.setPaymentMethod(event.target.value as CheckoutPaymentMethod)}>
                {paymentMethods.map((method) => (
                  <option key={method.value} value={method.value}>
                    {method.label}
                  </option>
                ))}
              </select>
            </label>
            {!authLoading && !isAuthenticated && (
              <div className="checkout-guest-grid">
                <label>
                  Nombre
                  <input className="input" value={checkout.guestFirstName} onChange={(event) => checkout.setGuestFirstName(event.target.value)} />
                </label>
                <label>
                  Apellido
                  <input className="input" value={checkout.guestLastName} onChange={(event) => checkout.setGuestLastName(event.target.value)} />
                </label>
                <label>
                  Email
                  <input className="input" type="email" value={checkout.guestEmail} onChange={(event) => checkout.setGuestEmail(event.target.value)} />
                </label>
                <label>
                  Telefono
                  <input className="input" value={checkout.guestPhone} onChange={(event) => checkout.setGuestPhone(event.target.value)} />
                </label>
              </div>
            )}
            <div className="checkout-actions">
              <Link className="btn btn-small btn-ghost" to="/home">
                Seguir comprando
              </Link>
            </div>
            <div className="checkout-actions">
              <button
                className="btn"
                type="button"
                onClick={() => void checkout.onFinalizeCheckout()}
                disabled={checkout.loading || authLoading}
              >
                {checkout.loading ? "Procesando..." : "Finalizar compra"}
              </button>
            </div>
            {checkout.error && <p className="error">{checkout.error}</p>}
            {checkout.success && <p className="success">{checkout.success}</p>}
          </div>
        </div>
      )}
    </section>
  );
}
