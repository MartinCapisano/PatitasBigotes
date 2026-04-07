import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  clearCart,
  decrementCartItem,
  incrementCartItem,
  readCart,
  removeCartItem,
  type CartItem
} from "../../../lib/cart-storage";
import {
  getMercadoPagoCheckoutUrl,
  redirectToMercadoPago,
  submitAuthenticatedCheckoutFromCart,
  submitGuestCheckoutFromCart,
  type CheckoutPaymentMethod
} from "../../../services/checkout-api";
import { classifyHttpError, toUserMessage } from "../../../services/http-errors";

export function useCheckoutPage(params: { authLoading: boolean; isAuthenticated: boolean }) {
  const { authLoading, isAuthenticated } = params;
  const navigate = useNavigate();
  const [items, setItems] = useState<CartItem[]>(() => readCart());
  const [guestFirstName, setGuestFirstName] = useState("");
  const [guestLastName, setGuestLastName] = useState("");
  const [guestEmail, setGuestEmail] = useState("");
  const [guestPhone, setGuestPhone] = useState("");
  const [paymentMethod, setPaymentMethod] = useState<CheckoutPaymentMethod>("bank_transfer");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const total = useMemo(
    () => items.reduce((sum, item) => sum + item.unit_price * item.quantity, 0),
    [items]
  );

  function clearCheckoutMessages() {
    setError("");
    setSuccess("");
  }

  function onIncrementItem(variantId: number, quantity: number) {
    if (loading) return;
    if (quantity >= 10) {
      setSuccess("");
      setError("La cantidad maxima por producto en checkout es 10.");
      return;
    }
    setItems(incrementCartItem(variantId, 10));
    clearCheckoutMessages();
  }

  function onDecrementItem(variantId: number, quantity: number) {
    if (loading || quantity <= 1) return;
    setItems(decrementCartItem(variantId));
    clearCheckoutMessages();
  }

  function onRemoveItem(variantId: number) {
    if (loading) return;
    setItems(removeCartItem(variantId));
    clearCheckoutMessages();
  }

  async function onFinalizeCheckout() {
    if (items.length === 0 || loading || authLoading) return;
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const result = isAuthenticated
        ? await submitAuthenticatedCheckoutFromCart(items, paymentMethod)
        : await submitGuestCheckoutFromCart(items, {
            first_name: guestFirstName.trim(),
            last_name: guestLastName.trim(),
            email: guestEmail.trim(),
            phone: guestPhone.trim()
          }, paymentMethod);
      const mercadoPagoCheckoutUrl = getMercadoPagoCheckoutUrl(result.payment);
      if (paymentMethod === "mercadopago") {
        if (!mercadoPagoCheckoutUrl) {
          throw new Error("No se pudo obtener la URL de MercadoPago para continuar el pago.");
        }
        clearCart();
        redirectToMercadoPago(mercadoPagoCheckoutUrl);
        return;
      }
      clearCart();
      if (result.payment) {
        if (result.payment.method === "cash") {
          setSuccess(
            `Compra enviada. Orden #${result.order.id} en estado ${result.order.status}. El pago en efectivo quedo pendiente de cobro y confirmacion presencial.`
          );
        } else {
          setSuccess(
            `Compra enviada. Orden #${result.order.id} (${result.order.status}). Pago #${result.payment.id} creado por ${result.payment.method}.`
          );
        }
      } else {
        setSuccess(`Compra enviada. Orden #${result.order.id} en estado ${result.order.status}. Pago acordado en efectivo.`);
      }
    } catch (apiError: unknown) {
      const classified = classifyHttpError(apiError);
      if (
        !isAuthenticated &&
        classified.kind === "conflict" &&
        classified.detail === "registered account requires login"
      ) {
        navigate("/login", {
          state: {
            from: "/checkout",
            checkoutEmail: guestEmail.trim(),
            reason: "registered_account_checkout"
          }
        });
        return;
      }
      setError(toUserMessage(apiError, "checkout"));
    } finally {
      setLoading(false);
    }
  }

  return {
    items,
    total,
    guestFirstName,
    setGuestFirstName,
    guestLastName,
    setGuestLastName,
    guestEmail,
    setGuestEmail,
    guestPhone,
    setGuestPhone,
    paymentMethod,
    setPaymentMethod,
    loading,
    error,
    success,
    onIncrementItem,
    onDecrementItem,
    onRemoveItem,
    onFinalizeCheckout
  };
}
