import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { MyOrder, MyPayment, MyProfile } from "../../../types";
import { getMercadoPagoCheckoutUrl, redirectToMercadoPago } from "../../../services/checkout-api";
import { getMyOrders, getMyProfile, requestEmailVerification, updateMyProfile } from "../../../services/auth-api";
import { toUserMessage } from "../../../services/http-errors";
import { listMyOrderPayments, retryMyOrderMercadoPago, uploadBankTransferReceipt } from "../../../services/payments-api";
import { savePendingVerificationEmail } from "../../auth/verification-storage";

const MAX_RECEIPT_SIZE_BYTES = 10 * 1024 * 1024;
const ALLOWED_RECEIPT_CONTENT_TYPES = new Set(["image/jpeg", "image/png", "application/pdf"]);
const RETRYABLE_MERCADOPAGO_STATUSES = new Set(["cancelled", "expired"]);

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
  const [receiptUploadingPaymentId, setReceiptUploadingPaymentId] = useState<number | null>(null);
  const [retryingPaymentId, setRetryingPaymentId] = useState<number | null>(null);
  const [paymentsByOrderId, setPaymentsByOrderId] = useState<Record<number, MyPayment[]>>({});
  const [receiptFiles, setReceiptFiles] = useState<Record<number, File | null>>({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [receiptError, setReceiptError] = useState("");
  const [receiptSuccess, setReceiptSuccess] = useState("");
  const [retryError, setRetryError] = useState("");
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

  function onSelectReceiptFile(paymentId: number, file: File | null) {
    setReceiptError("");
    setReceiptSuccess("");
    setReceiptFiles((prev) => ({ ...prev, [paymentId]: file }));
  }

  function onContinueMercadoPagoPayment(payment: MyPayment) {
    setRetryError("");
    const checkoutUrl = getMercadoPagoCheckoutUrl(payment);
    if (!checkoutUrl) {
      setRetryError("No pudimos obtener el nuevo enlace de pago.");
      return;
    }
    try {
      redirectToMercadoPago(checkoutUrl);
    } catch {
      setRetryError("No pudimos redirigirte automaticamente. Puedes continuar el pago desde este boton.");
    }
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
    setReceiptError("");
    setReceiptSuccess("");
    try {
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

      const updatedPayment = await retryMyOrderMercadoPago(orderId);
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
      } catch {
        setRetryError("No pudimos redirigirte automaticamente. Puedes continuar el pago desde este boton.");
      }
    } catch (apiError: unknown) {
      setRetryError(toUserMessage(apiError, "profile"));
    } finally {
      setRetryingPaymentId(null);
    }
  }

  async function onUploadReceipt(orderId: number, paymentId: number) {
    const file = receiptFiles[paymentId] ?? null;
    if (!file || receiptUploadingPaymentId !== null) return;
    if (!ALLOWED_RECEIPT_CONTENT_TYPES.has(file.type)) {
      setReceiptError("Formato de comprobante no permitido. Usa JPG, PNG o PDF.");
      setReceiptSuccess("");
      return;
    }
    if (file.size <= 0) {
      setReceiptError("El archivo seleccionado esta vacio.");
      setReceiptSuccess("");
      return;
    }
    if (file.size > MAX_RECEIPT_SIZE_BYTES) {
      setReceiptError("El comprobante supera el tamano maximo permitido de 10 MB.");
      setReceiptSuccess("");
      return;
    }

    setReceiptUploadingPaymentId(paymentId);
    setReceiptError("");
    setReceiptSuccess("");
    try {
      const updatedPayment = await uploadBankTransferReceipt(orderId, paymentId, file);
      setPaymentsByOrderId((prev) => ({
        ...prev,
        [orderId]: (prev[orderId] ?? []).map((payment) => (payment.id === paymentId ? updatedPayment : payment))
      }));
      setReceiptFiles((prev) => ({ ...prev, [paymentId]: null }));
      setReceiptSuccess("Comprobante cargado correctamente.");
    } catch (apiError: unknown) {
      setReceiptError(toUserMessage(apiError, "profile"));
    } finally {
      setReceiptUploadingPaymentId(null);
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
    receiptUploadingPaymentId,
    retryingPaymentId,
    paymentsByOrderId,
    receiptFiles,
    error,
    success,
    receiptError,
    receiptSuccess,
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
    onSelectReceiptFile,
    onUploadReceipt,
    isRetryableMercadoPagoPayment,
    onRetryMercadoPago,
    onContinueMercadoPagoPayment
  };
}
