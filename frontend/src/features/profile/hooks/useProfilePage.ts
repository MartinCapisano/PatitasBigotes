import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { MyOrder, MyPayment, MyProfile } from "../../../types";
import { getMercadoPagoCheckoutUrl, redirectToMercadoPago } from "../../../services/checkout-api";
import { getMyOrders, getMyProfile, requestEmailVerification, updateMyProfile } from "../../../services/auth-api";
import { toUserMessage } from "../../../services/http-errors";
import { buildIdempotencyKey } from "../../../services/idempotency";
import { listMyOrderPayments, retryMyOrderMercadoPago } from "../../../services/payments-api";
import { savePendingVerificationEmail } from "../../auth/verification-storage";

const RETRYABLE_MERCADOPAGO_STATUSES = new Set(["cancelled", "expired"]);

type ActiveRetryAttempt = {
  orderId: number;
  sourcePaymentId: number;
  idempotencyKey: string;
  payment: MyPayment | null;
};

export function useProfilePage() {
  const navigate = useNavigate();
  const [section, setSection] = useState<"profile" | "history">("profile");
  const [profile, setProfile] = useState<MyProfile | null>(null);
  const [orders, setOrders] = useState<MyOrder[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [ordersError, setOrdersError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [verificationLoading, setVerificationLoading] = useState(false);
  const [retryingPaymentId, setRetryingPaymentId] = useState<number | null>(null);
  const [paymentsByOrderId, setPaymentsByOrderId] = useState<Record<number, MyPayment[]>>({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [retryError, setRetryError] = useState("");
  const activeRetryAttemptRef = useRef<ActiveRetryAttempt | null>(null);
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [editingField, setEditingField] = useState<"phone" | "email" | null>(null);

  async function loadProfile() {
    setLoading(true);
    setError("");
    try {
      const data = await getMyProfile();
      setProfile(data);
      setPhone(data.phone || "");
      setEmail(data.email || "");
    } catch (apiError: unknown) {
      setError(toUserMessage(apiError, "profile"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadProfile();
  }, []);

  useEffect(() => {
    async function loadOrders() {
      if (section !== "history") return;
      setOrdersLoading(true);
      try {
        await refreshOrders();
      } catch (apiError: unknown) {
        setOrdersError(toUserMessage(apiError, "profile"));
      } finally {
        setOrdersLoading(false);
      }
    }
    void loadOrders();
  }, [section]);

  async function refreshOrders() {
    setOrdersError("");
    const nextOrders = await getMyOrders();
    setOrders(nextOrders);
    const paymentsByOrderEntries = await Promise.all(
      nextOrders.map(async (order) => [order.id, await listMyOrderPayments(order.id)] as const)
    );
    const nextPaymentsByOrderId = Object.fromEntries(paymentsByOrderEntries);
    setPaymentsByOrderId(nextPaymentsByOrderId);
    return {
      orders: nextOrders,
      paymentsByOrderId: nextPaymentsByOrderId,
    };
  }

  async function refreshOrderPayments(orderId: number) {
    const payments = await listMyOrderPayments(orderId);
    setPaymentsByOrderId((prev) => ({
      ...prev,
      [orderId]: payments
    }));
    return payments;
  }

  function onStartEditing(field: "phone" | "email") {
    if (!profile) return;
    setError("");
    setSuccess("");
    setPhone(profile.phone || "");
    setEmail(profile.email || "");
    setEditingField(field);
  }

  function onCancelEditing() {
    if (profile) {
      setPhone(profile.phone || "");
      setEmail(profile.email || "");
    }
    setEditingField(null);
    setError("");
  }

  async function onSaveField(field: "phone" | "email") {
    if (!profile) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const previousEmail = profile.email;
      const result = await updateMyProfile({
        first_name: profile.first_name,
        last_name: profile.last_name,
        phone: phone.trim(),
        email: email.trim()
      });
      setProfile(result.data);
      setPhone(result.data.phone || "");
      setEmail(result.data.email || "");
      setEditingField(null);
      const verificationSent = Boolean((result.meta as Record<string, unknown>).verification_email_sent);
      if (field === "email" && verificationSent && previousEmail.trim().toLowerCase() !== email.trim().toLowerCase()) {
        savePendingVerificationEmail(result.data.email || email.trim());
        setSuccess("Email actualizado. Te enviamos una verificacion a tu nuevo correo.");
      } else if (field === "email") {
        setSuccess("Email actualizado.");
      } else {
        setSuccess("Telefono actualizado.");
      }
    } catch (apiError: unknown) {
      setError(toUserMessage(apiError, "profile"));
    } finally {
      setSaving(false);
    }
  }

  async function onRequestEmailVerification() {
    if (!profile || !profile.email || verificationLoading) return;
    setVerificationLoading(true);
    setError("");
    setSuccess("");
    try {
      await requestEmailVerification(profile.email);
      savePendingVerificationEmail(profile.email);
      setSuccess("Te enviamos un email de verificacion a tu correo actual.");
      navigate("/verify-email");
    } catch (apiError: unknown) {
      setError(toUserMessage(apiError, "email-verify"));
    } finally {
      setVerificationLoading(false);
    }
  }

  function onContinueMercadoPagoPayment(payment: MyPayment) {
    setRetryError("");
    const activeRetryAttempt = activeRetryAttemptRef.current;
    const paymentForContinue =
      activeRetryAttempt?.payment &&
      activeRetryAttempt.orderId === payment.order_id
        ? activeRetryAttempt.payment
        : payment;
    const checkoutUrl = getMercadoPagoCheckoutUrl(paymentForContinue);
    if (!checkoutUrl) {
      setRetryError("No pudimos obtener el nuevo enlace de pago.");
      return;
    }
    try {
      redirectToMercadoPago(checkoutUrl);
      activeRetryAttemptRef.current = null;
    } catch {
      setRetryError("No pudimos redirigirte automaticamente. Puedes continuar el pago desde este boton.");
    }
  }

  function hasActiveRetryCheckoutForPayment(orderId: number, paymentId: number) {
    const activeRetryAttempt = activeRetryAttemptRef.current;
    return (
      activeRetryAttempt !== null &&
      activeRetryAttempt.orderId === orderId &&
      activeRetryAttempt.sourcePaymentId === paymentId &&
      activeRetryAttempt.payment !== null
    );
  }

  function isRetryableMercadoPagoPayment(payment: MyPayment) {
    return (
      payment.method === "mercadopago" &&
      (
        RETRYABLE_MERCADOPAGO_STATUSES.has(payment.status) ||
        (payment.status === "pending" && payment.provider_status === "setup_failed")
      )
    );
  }

  async function onRetryMercadoPago(orderId: number, paymentId: number) {
    if (retryingPaymentId !== null) return;

    setRetryingPaymentId(paymentId);
    setRetryError("");
    try {
      const existingAttempt = activeRetryAttemptRef.current;
      if (
        existingAttempt?.payment &&
        existingAttempt.orderId === orderId &&
        existingAttempt.sourcePaymentId === paymentId
      ) {
        const checkoutUrl = getMercadoPagoCheckoutUrl(existingAttempt.payment);
        if (!checkoutUrl) {
          setRetryError("No pudimos obtener el nuevo enlace de pago.");
          return;
        }
        redirectToMercadoPago(checkoutUrl);
        activeRetryAttemptRef.current = null;
        return;
      }
      const idempotencyKey =
        existingAttempt?.orderId === orderId &&
        existingAttempt.sourcePaymentId === paymentId
          ? existingAttempt.idempotencyKey
          : buildIdempotencyKey(`retry_order_payment_${orderId}_mercadopago`);
      activeRetryAttemptRef.current = {
        orderId,
        sourcePaymentId: paymentId,
        idempotencyKey,
        payment: existingAttempt?.orderId === orderId && existingAttempt.sourcePaymentId === paymentId
          ? existingAttempt.payment
          : null,
      };
      const freshData = await refreshOrders();
      const freshOrder = freshData.orders.find((order) => order.id === orderId) ?? null;
      const freshPayment =
        (freshData.paymentsByOrderId[orderId] ?? []).find((payment) => payment.id === paymentId) ?? null;

      if (!freshOrder || freshOrder.status !== "submitted") {
        setRetryError("La orden ya no esta disponible para reintentar el pago.");
        return;
      }
      if (!freshPayment || !isRetryableMercadoPagoPayment(freshPayment)) {
        setRetryError("Este pago ya no puede reintentarse desde aqui.");
        return;
      }

      const updatedPayment = await retryMyOrderMercadoPago(orderId, idempotencyKey);
      activeRetryAttemptRef.current = {
        orderId,
        sourcePaymentId: paymentId,
        idempotencyKey,
        payment: updatedPayment,
      };
      const refreshedPayments = await refreshOrderPayments(orderId);
      const paymentForRedirect =
        refreshedPayments.find((payment) => payment.id === updatedPayment.id) ?? updatedPayment;
      const checkoutUrl = getMercadoPagoCheckoutUrl(paymentForRedirect);
      if (!checkoutUrl) {
        setRetryError("No pudimos obtener el nuevo enlace de pago.");
        return;
      }
      try {
        redirectToMercadoPago(checkoutUrl);
        activeRetryAttemptRef.current = null;
      } catch {
        setRetryError("No pudimos redirigirte automaticamente. Puedes continuar el pago desde este boton.");
      }
    } catch (apiError: unknown) {
      setRetryError(toUserMessage(apiError, "profile"));
    } finally {
      setRetryingPaymentId(null);
    }
  }

  return {
    section,
    setSection,
    profile,
    orders,
    ordersLoading,
    ordersError,
    loading,
    saving,
    verificationLoading,
    retryingPaymentId,
    paymentsByOrderId,
    error,
    success,
    retryError,
    phone,
    setPhone,
    email,
    setEmail,
    editingField,
    onStartEditing,
    onCancelEditing,
    onSaveField,
    onRequestEmailVerification,
    hasActiveRetryCheckoutForPayment,
    isRetryableMercadoPagoPayment,
    onRetryMercadoPago,
    onContinueMercadoPagoPayment
  };
}
