import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { getMercadoPagoCheckoutUrl, redirectToMercadoPago } from "../../../services/checkout-api";
import { toUserMessage } from "../../../services/http-errors";
import { buildIdempotencyKey } from "../../../services/idempotency";
import {
  fetchPublicOrderSnapshotByPaymentToken,
  retryGuestMercadoPago,
  type PublicPaymentStatus
} from "../../../services/payments-api";
import type { MyPayment, PublicOrderSnapshot } from "../../../types";

type ActiveRetryAttempt = {
  idempotencyKey: string;
  payment: MyPayment | null;
};

export function usePaymentReturnStatus() {
  const location = useLocation();
  const [status, setStatus] = useState<PublicPaymentStatus | null>(null);
  const [snapshot, setSnapshot] = useState<PublicOrderSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState("");
  const [retryError, setRetryError] = useState("");
  const activeRetryAttemptRef = useRef<ActiveRetryAttempt | null>(null);
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

  function clearActiveRetryAttempt() {
    activeRetryAttemptRef.current = null;
  }

  function getActiveRetryPayment(): MyPayment | null {
    return activeRetryAttemptRef.current?.payment ?? null;
  }

  function getContinueCheckoutUrl(): string | null {
    const activeRetryPayment = getActiveRetryPayment();
    if (activeRetryPayment) {
      return getMercadoPagoCheckoutUrl(activeRetryPayment);
    }
    return snapshot?.payment.checkout_url?.trim() || null;
  }

  function onContinuePayment() {
    setRetryError("");
    const checkoutUrl = getContinueCheckoutUrl();
    if (!checkoutUrl) {
      setRetryError("No pudimos obtener el enlace de pago.");
      return;
    }
    if (!getActiveRetryPayment() && !snapshot?.flags.can_continue_payment) {
      setRetryError("Este pago ya no esta disponible para continuar.");
      return;
    }
    try {
      redirectToMercadoPago(checkoutUrl);
      clearActiveRetryAttempt();
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
      const existingAttempt = activeRetryAttemptRef.current;
      if (existingAttempt?.payment) {
        const checkoutUrl = getMercadoPagoCheckoutUrl(existingAttempt.payment);
        if (!checkoutUrl) {
          setRetryError("No pudimos obtener el nuevo enlace de pago.");
          await loadSnapshot();
          return;
        }
        redirectToMercadoPago(checkoutUrl);
        clearActiveRetryAttempt();
        return;
      }
      const idempotencyKey =
        existingAttempt?.idempotencyKey ??
        buildIdempotencyKey(`retry_guest_payment_${lookup.publicStatusToken}`);
      activeRetryAttemptRef.current = {
        idempotencyKey,
        payment: existingAttempt?.payment ?? null,
      };
      const payment = await retryGuestMercadoPago(lookup.publicStatusToken, idempotencyKey);
      activeRetryAttemptRef.current = {
        idempotencyKey,
        payment,
      };
      const checkoutUrl = getMercadoPagoCheckoutUrl(payment);
      if (!checkoutUrl) {
        setRetryError("No pudimos obtener el nuevo enlace de pago.");
        await loadSnapshot();
        return;
      }
      redirectToMercadoPago(checkoutUrl);
      clearActiveRetryAttempt();
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
    hasActiveRetryCheckout: getActiveRetryPayment() !== null,
    error,
    retryError,
    loadStatus: loadSnapshot,
    loadSnapshot,
    onContinuePayment,
    onRetryPayment
  };
}
