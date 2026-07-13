import { useEffect, useState } from "react";
import {
  getAdminOrder,
  listAdminOrderPayments,
  listAdminOrders,
  listAdminPayments,
  registerAdminOrderManualPayment,
  type AdminOrder,
  type AdminPayment
} from "../../../services/admin-orders-api";
import { createAdminSale } from "../../../services/admin-sales-api";
import type { AdminSection, ManualOrderItem, VariantOption } from "../types";

export function useAdminOrdersPayments(params: {
  adminSection: AdminSection;
  variantOptions: VariantOption[];
}) {
  const { adminSection, variantOptions } = params;
  const [orderError, setOrderError] = useState("");
  const [orderSuccess, setOrderSuccess] = useState("");
  const [selectedOrder, setSelectedOrder] = useState<AdminOrder | null>(null);
  const [orderPayments, setOrderPayments] = useState<AdminPayment[]>([]);
  const [ordersList, setOrdersList] = useState<AdminOrder[]>([]);
  const [ordersListLoading, setOrdersListLoading] = useState(false);
  const [ordersFilter, setOrdersFilter] = useState<"all" | "submitted" | "paid" | "cancelled">("all");
  const [ordersShowAll, setOrdersShowAll] = useState(false);
  const [ordersSortBy, setOrdersSortBy] = useState<"created_at" | "id">("created_at");
  const [ordersSortDir, setOrdersSortDir] = useState<"desc" | "asc">("desc");
  const [paymentsList, setPaymentsList] = useState<AdminPayment[]>([]);
  const [paymentsListLoading, setPaymentsListLoading] = useState(false);
  const [paymentsFilter, setPaymentsFilter] = useState<"all" | "pending" | "paid" | "cancelled" | "expired">("all");
  const [paymentsShowAll, setPaymentsShowAll] = useState(false);
  const [paymentsSortBy, setPaymentsSortBy] = useState<"created_at" | "id">("created_at");
  const [paymentsSortDir, setPaymentsSortDir] = useState<"desc" | "asc">("desc");
  const [showCreateManualOrderForm, setShowCreateManualOrderForm] = useState(false);
  const [showManualPaymentForm, setShowManualPaymentForm] = useState(false);
  const [manualEmail, setManualEmail] = useState("");
  const [manualFirstName, setManualFirstName] = useState("");
  const [manualLastName, setManualLastName] = useState("");
  const [manualPhone, setManualPhone] = useState("");
  const [manualVariantId, setManualVariantId] = useState("");
  const [manualQuantity, setManualQuantity] = useState("1");
  const [manualItems, setManualItems] = useState<ManualOrderItem[]>([]);
  const [manualPayRef, setManualPayRef] = useState("");
  const [manualPayAmount, setManualPayAmount] = useState("");
  const [loadingOrderDetail, setLoadingOrderDetail] = useState(false);
  const [creatingManualOrder, setCreatingManualOrder] = useState(false);
  const [markingOrderPaid, setMarkingOrderPaid] = useState(false);

  async function loadAdminOrder(orderId: number) {
    setLoadingOrderDetail(true);
    try {
      const [order, payments] = await Promise.all([getAdminOrder(orderId), listAdminOrderPayments(orderId)]);
      setSelectedOrder(order);
      setOrderPayments(payments);
    } finally {
      setLoadingOrderDetail(false);
    }
  }

  function closeSelectedOrder() {
    setSelectedOrder(null);
    setOrderPayments([]);
  }

  function onAddManualItem() {
    const parsedVariantId = Number.parseInt(manualVariantId, 10);
    const parsedQty = Number.parseInt(manualQuantity, 10);
    if (Number.isNaN(parsedVariantId) || parsedVariantId <= 0 || Number.isNaN(parsedQty) || parsedQty <= 0) {
      setOrderError("Item invalido para la orden manual.");
      return;
    }
    const option = variantOptions.find((row) => row.value === String(parsedVariantId));
    const label = option?.label || `Variante ${parsedVariantId}`;
    const existing = manualItems.find((row) => row.variant_id === parsedVariantId);
    if (existing) {
      setManualItems((prev) =>
        prev.map((row) => (row.variant_id === parsedVariantId ? { ...row, quantity: row.quantity + parsedQty } : row))
      );
    } else {
      setManualItems((prev) => [...prev, { variant_id: parsedVariantId, quantity: parsedQty, label }]);
    }
    setManualVariantId("");
    setManualQuantity("1");
    setOrderError("");
  }

  function removeManualItem(variantId: number) {
    setManualItems((prev) => prev.filter((row) => row.variant_id !== variantId));
  }

  async function onCreateManualOrder() {
    setOrderError("");
    setOrderSuccess("");
    if (manualItems.length === 0) {
      setOrderError("Agrega al menos un item.");
      return;
    }
    setCreatingManualOrder(true);
    try {
      const response = await createAdminSale({
        customer: {
          mode: "new",
          email: manualEmail.trim(),
          first_name: manualFirstName.trim(),
          last_name: manualLastName.trim(),
          phone: manualPhone.trim()
        },
        items: manualItems.map((row) => ({ variant_id: row.variant_id, quantity: row.quantity })),
        register_payment: false
      });
      const orderId = response.order.id;
      await loadAdminOrder(orderId);
      setOrderSuccess(`Orden manual creada: #${orderId}`);
      setManualItems([]);
      setShowCreateManualOrderForm(false);
    } catch {
      setOrderError("No se pudo crear la orden manual.");
    } finally {
      setCreatingManualOrder(false);
    }
  }

  async function onMarkOrderPaid() {
    if (!selectedOrder) return;
    const parsedAmount = Number.parseInt(manualPayAmount, 10);
    if (Number.isNaN(parsedAmount) || parsedAmount <= 0) {
      setOrderError("Monto invalido para confirmar pago manual.");
      return;
    }
    if (!manualPayRef.trim()) {
      setOrderError("Payment ref requerida.");
      return;
    }
    setOrderError("");
    setOrderSuccess("");
    setMarkingOrderPaid(true);
    try {
      const result = await registerAdminOrderManualPayment({
        order_id: selectedOrder.id,
        method: "bank_transfer",
        paid_amount: parsedAmount,
        payment_ref: manualPayRef.trim()
      });
      setSelectedOrder(result.order);
      await loadAdminOrder(selectedOrder.id);
      setOrderSuccess(`Orden #${selectedOrder.id} marcada como pagada.`);
    } catch {
      setOrderError("No se pudo marcar la orden como pagada.");
    } finally {
      setMarkingOrderPaid(false);
    }
  }

  useEffect(() => {
    async function loadOrdersPanelList() {
      if (adminSection !== "ordenes") return;
      setOrdersListLoading(true);
      setOrderError("");
      try {
        const rows = await listAdminOrders({
          status: ordersFilter === "all" ? undefined : ordersFilter,
          limit: ordersShowAll ? 500 : 10,
          sort_by: ordersSortBy,
          sort_dir: ordersSortDir
        });
        setOrdersList(rows);
      } catch {
        setOrderError("No se pudieron cargar las ordenes.");
      } finally {
        setOrdersListLoading(false);
      }
    }
    void loadOrdersPanelList();
  }, [adminSection, ordersFilter, ordersShowAll, ordersSortBy, ordersSortDir]);

  useEffect(() => {
    async function loadPaymentsPanelList() {
      if (adminSection !== "pagos") return;
      setPaymentsListLoading(true);
      setOrderError("");
      try {
        const rows = await listAdminPayments({
          status: paymentsFilter === "all" ? undefined : paymentsFilter,
          limit: paymentsShowAll ? 500 : 10,
          sort_by: paymentsSortBy,
          sort_dir: paymentsSortDir
        });
        setPaymentsList(rows);
      } catch {
        setOrderError("No se pudieron cargar los pagos.");
      } finally {
        setPaymentsListLoading(false);
      }
    }
    void loadPaymentsPanelList();
  }, [adminSection, paymentsFilter, paymentsShowAll, paymentsSortBy, paymentsSortDir]);

  return {
    orderError,
    orderSuccess,
    showCreateManualOrderForm,
    setShowCreateManualOrderForm,
    ordersFilter,
    setOrdersFilter,
    ordersSortBy,
    setOrdersSortBy,
    ordersSortDir,
    setOrdersSortDir,
    ordersShowAll,
    setOrdersShowAll,
    manualEmail,
    setManualEmail,
    manualFirstName,
    setManualFirstName,
    manualLastName,
    setManualLastName,
    manualPhone,
    setManualPhone,
    manualVariantId,
    setManualVariantId,
    manualQuantity,
    setManualQuantity,
    onAddManualItem,
    manualItems,
    removeManualItem,
    setManualItems,
    onCreateManualOrder,
    ordersListLoading,
    ordersList,
    loadAdminOrder,
    closeSelectedOrder,
    paymentsFilter,
    setPaymentsFilter,
    paymentsSortBy,
    setPaymentsSortBy,
    paymentsSortDir,
    setPaymentsSortDir,
    paymentsShowAll,
    setPaymentsShowAll,
    showManualPaymentForm,
    setShowManualPaymentForm,
    paymentsListLoading,
    paymentsList,
    selectedOrder,
    orderPayments,
    manualPayRef,
    setManualPayRef,
    manualPayAmount,
    setManualPayAmount,
    onMarkOrderPaid,
    loadingOrderDetail,
    creatingManualOrder,
    markingOrderPaid
  };
}
