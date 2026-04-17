import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { getMercadoPagoCheckoutUrl, redirectToMercadoPago } from "../../../services/checkout-api";
import { toUserMessage } from "../../../services/http-errors";
import {
  fetchPublicOrderSnapshotByPaymentToken,
  retryGuestMercadoPago,
  type PublicPaymentStatus
} from "../../../services/payments-api";
import type { PublicOrderSnapshot } from "../../../types";

export function usePaymentReturnStatus() {
  const location = useLocation();
  const [status, setStatus] = useState<PublicPaymentStatus | null>(null);
  const [snapshot, setSnapshot] = useState<PublicOrderSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState("");
  const [retryError, setRetryError] = useState("");
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const lookup = useMemo(
    () => ({
      publicStatusToken: params.get("public_status_token"),
    }),
    [params]
  );

  async function loadSnapshot() {
    if (!lookup.publicStatusToken) {
      setError("No encontramos el identificador publico del pago.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const nextSnapshot = await fetchPublicOrderSnapshotByPaymentToken(lookup);
      setSnapshot(nextSnapshot);
      setStatus({
        order_status: nextSnapshot.order.status,
        status: nextSnapshot.payment.status,
        updated_at: null,
        paid_at: null,
      });
    } catch (apiError: unknown) {
      setSnapshot(null);
      setStatus(null);
      setError(toUserMessage(apiError, "payment-return"));
    } finally {
      setLoading(false);
    }
  }

  function onContinuePayment() {
    setRetryError("");
    if (!snapshot?.flags.can_continue_payment) {
      setRetryError("Este pago ya no esta disponible para continuar.");
      return;
    }
    const checkoutUrl = snapshot.payment.checkout_url?.trim() || null;
    if (!checkoutUrl) {
      setRetryError("No pudimos obtener el enlace de pago.");
      return;
    }
    try {
      redirectToMercadoPago(checkoutUrl);
    } catch {
      setRetryError("No pudimos redirigirte automaticamente. Intenta nuevamente.");
    }
  }

  async function onRetryPayment() {
    if (!lookup.publicStatusToken || retrying) {
      return;
    }
    if (!snapshot?.flags.can_retry_payment) {
      setRetryError("Este pago ya no puede reintentarse desde aqui.");
      return;
    }

    setRetrying(true);
    setRetryError("");
    try {
      const payment = await retryGuestMercadoPago(lookup.publicStatusToken);
      const checkoutUrl = getMercadoPagoCheckoutUrl(payment);
      if (!checkoutUrl) {
        setRetryError("No pudimos obtener el nuevo enlace de pago.");
        await loadSnapshot();
        return;
      }
      redirectToMercadoPago(checkoutUrl);
    } catch (apiError: unknown) {
      setRetryError(toUserMessage(apiError, "payment-return"));
      await loadSnapshot();
    } finally {
      setRetrying(false);
    }
  }

  useEffect(() => {
    void loadSnapshot();
  }, [lookup.publicStatusToken]);

  return {
    location,
    status,
    snapshot,
    loading,
    retrying,
    error,
    retryError,
    loadStatus: loadSnapshot,
    loadSnapshot,
    onContinuePayment,
    onRetryPayment
  };
}
