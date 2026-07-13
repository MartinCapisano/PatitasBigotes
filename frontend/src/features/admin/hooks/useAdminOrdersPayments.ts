import { useEffect, useState } from "react";
import {
  getAdminOrder,
  listAdminOrderPayments,
  listAdminOrders,
  listAdminPayments,
  type AdminOrder,
  type AdminPayment
} from "../../../services/admin-orders-api";
import type { AdminSection } from "../types";

export function useAdminOrdersPayments(params: { adminSection: AdminSection }) {
  const { adminSection } = params;
  const [orderError, setOrderError] = useState("");
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
  const [loadingOrderDetail, setLoadingOrderDetail] = useState(false);

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
    ordersFilter,
    setOrdersFilter,
    ordersSortBy,
    setOrdersSortBy,
    ordersSortDir,
    setOrdersSortDir,
    ordersShowAll,
    setOrdersShowAll,
    ordersListLoading,
    ordersList,
    loadAdminOrder,
    loadingOrderDetail,
    closeSelectedOrder,
    paymentsFilter,
    setPaymentsFilter,
    paymentsSortBy,
    setPaymentsSortBy,
    paymentsSortDir,
    setPaymentsSortDir,
    paymentsShowAll,
    setPaymentsShowAll,
    paymentsListLoading,
    paymentsList,
    selectedOrder,
    orderPayments
  };
}
