import { useModalA11y } from "../../../lib/useModalA11y";
import type { AdminOrder, AdminPayment } from "../services";
import type { AdminSection } from "../types";

export function OrdersPaymentsSection(props: {
  adminSection: AdminSection;
  orderError: string;
  ordersFilter: "all" | "submitted" | "paid" | "cancelled";
  setOrdersFilter: (value: "all" | "submitted" | "paid" | "cancelled") => void;
  ordersSortBy: "created_at" | "id";
  setOrdersSortBy: (value: "created_at" | "id") => void;
  ordersSortDir: "desc" | "asc";
  setOrdersSortDir: (value: "desc" | "asc") => void;
  ordersShowAll: boolean;
  setOrdersShowAll: (value: boolean | ((prev: boolean) => boolean)) => void;
  ordersListLoading: boolean;
  ordersList: AdminOrder[];
  loadAdminOrder: (orderId: number) => Promise<void>;
  loadingOrderDetail: boolean;
  closeSelectedOrder: () => void;
  paymentsFilter: "all" | "pending" | "paid" | "cancelled" | "expired";
  setPaymentsFilter: (value: "all" | "pending" | "paid" | "cancelled" | "expired") => void;
  paymentsSortBy: "created_at" | "id";
  setPaymentsSortBy: (value: "created_at" | "id") => void;
  paymentsSortDir: "desc" | "asc";
  setPaymentsSortDir: (value: "desc" | "asc") => void;
  paymentsShowAll: boolean;
  setPaymentsShowAll: (value: boolean | ((prev: boolean) => boolean)) => void;
  paymentsListLoading: boolean;
  paymentsList: AdminPayment[];
  selectedOrder: AdminOrder | null;
  orderPayments: AdminPayment[];
  formatArs: (cents: number | null) => string;
}) {
  const {
    adminSection,
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
    orderPayments,
    formatArs
  } = props;

  const orderDetailModalRef = useModalA11y<HTMLDivElement>(Boolean(selectedOrder), closeSelectedOrder);

  return (
    <article className="card admin-orders-section">
      <h2>{adminSection === "ordenes" ? "Admin Ordenes" : "Admin Pagos"}</h2>
      <p className="muted">
        {adminSection === "ordenes"
          ? "Ultimas ordenes, filtros por estado y orden por fecha o id."
          : "Ultimos pagos, filtros por estado y orden por fecha o id."}
      </p>
      {orderError && <p className="error">{orderError}</p>}

      {adminSection === "ordenes" && (
        <>
          <div className="admin-inline-actions">
            <select className="input" value={ordersFilter} onChange={(e) => setOrdersFilter(e.target.value as "all" | "submitted" | "paid" | "cancelled")}>
              <option value="all">Todas</option>
              <option value="submitted">Submitted</option>
              <option value="paid">Paid</option>
              <option value="cancelled">Cancelled</option>
            </select>
            <select className="input" value={ordersSortBy} onChange={(e) => setOrdersSortBy(e.target.value as "created_at" | "id")}>
              <option value="created_at">Ordenar por fecha</option>
              <option value="id">Ordenar por ID</option>
            </select>
            <select className="input" value={ordersSortDir} onChange={(e) => setOrdersSortDir(e.target.value as "desc" | "asc")}>
              <option value="desc">Desc</option>
              <option value="asc">Asc</option>
            </select>
            <button className="btn btn-small" type="button" onClick={() => setOrdersShowAll((v) => !v)}>
              {ordersShowAll ? "Mostrar ultimas 10" : "Mostrar todas"}
            </button>
          </div>

          <h3>Listado de ordenes</h3>
          {ordersListLoading ? (
            <p>Cargando ordenes...</p>
          ) : ordersList.length === 0 ? (
            <p className="muted">Sin ordenes para mostrar.</p>
          ) : (
            <div className="admin-scroll-list">
              {ordersList.map((order) => (
                <div className="admin-variant-row" key={order.id}>
                  <p><strong>#{order.id}</strong></p>
                  <p className="muted">Estado: {order.status}</p>
                  <p className="muted">Total: {formatArs(order.total_amount)}</p>
                  <div className="admin-product-actions">
                    <button className="btn btn-small" type="button" onClick={() => void loadAdminOrder(order.id)} disabled={loadingOrderDetail}>
                      {loadingOrderDetail ? "Cargando..." : "Ver detalle"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
      {adminSection === "pagos" && (
        <>
          <div className="admin-inline-actions">
            <select className="input" value={paymentsFilter} onChange={(e) => setPaymentsFilter(e.target.value as "all" | "pending" | "paid" | "cancelled" | "expired")}>
              <option value="all">Todos</option>
              <option value="pending">Pending</option>
              <option value="paid">Paid</option>
              <option value="cancelled">Cancelled</option>
              <option value="expired">Expired</option>
            </select>
            <select className="input" value={paymentsSortBy} onChange={(e) => setPaymentsSortBy(e.target.value as "created_at" | "id")}>
              <option value="created_at">Ordenar por fecha</option>
              <option value="id">Ordenar por ID</option>
            </select>
            <select className="input" value={paymentsSortDir} onChange={(e) => setPaymentsSortDir(e.target.value as "desc" | "asc")}>
              <option value="desc">Desc</option>
              <option value="asc">Asc</option>
            </select>
            <button className="btn btn-small" type="button" onClick={() => setPaymentsShowAll((v) => !v)}>
              {paymentsShowAll ? "Mostrar ultimos 10" : "Mostrar todos"}
            </button>
          </div>
          <h3>Listado de pagos</h3>
          {paymentsListLoading ? (
            <p>Cargando pagos...</p>
          ) : paymentsList.length === 0 ? (
            <p className="muted">Sin pagos para mostrar.</p>
          ) : (
            <div className="admin-scroll-list">
              {paymentsList.map((payment) => (
                <div className="admin-variant-row" key={payment.id}>
                  <p><strong>#{payment.id}</strong> {payment.method}</p>
                  <p className="muted">Estado: {payment.status}</p>
                  <p className="muted">Monto: {formatArs(payment.amount)}</p>
                  {payment.has_open_incident ? <p className="error">Incidencia pago tardio pendiente</p> : null}
                  <div className="admin-product-actions">
                    <button
                      className="btn btn-small"
                      type="button"
                      onClick={() => void loadAdminOrder(payment.order_id)}
                      disabled={loadingOrderDetail}
                    >
                      {loadingOrderDetail ? "Cargando..." : `Ver orden #${payment.order_id}`}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {selectedOrder && (
        <div
          className="admin-modal-overlay"
          role="dialog"
          aria-modal="true"
          ref={orderDetailModalRef}
          tabIndex={-1}
        >
          <div className="card admin-modal">
            <div className="admin-modal-header">
              <h3>Detalle de orden</h3>
              <button className="btn btn-small btn-ghost" type="button" onClick={closeSelectedOrder}>
                Cerrar
              </button>
            </div>
            <p>
              <strong>Orden #{selectedOrder.id}</strong> | Estado: {selectedOrder.status} | Total: {formatArs(selectedOrder.total_amount)}
            </p>
            <div className="admin-form-grid">
              <p><strong>Nombre:</strong> {selectedOrder.customer?.first_name || "-"}</p>
              <p><strong>Apellido:</strong> {selectedOrder.customer?.last_name || "-"}</p>
              <p><strong>Telefono:</strong> {selectedOrder.customer?.phone || "-"}</p>
              <p><strong>Email:</strong> {selectedOrder.customer?.email || "-"}</p>
            </div>
            <div className="admin-variants-grid">
              {selectedOrder.items.map((item) => (
                <div className="admin-variant-row" key={item.id}>
                  <p>
                    {item.product_name || "Producto"} - {item.variant_label}
                  </p>
                  <p className="muted">Qty: {item.quantity}</p>
                  <p className="muted">Subtotal linea: {formatArs(item.line_total)}</p>
                </div>
              ))}
            </div>

            {adminSection === "pagos" && (
              <>
                <h4>Pagos</h4>
                {orderPayments.length === 0 ? (
                  <p className="muted">Sin pagos para esta orden.</p>
                ) : (
                  <div className="admin-variants-grid">
                    {orderPayments.map((payment) => (
                      <div className="admin-variant-row" key={payment.id}>
                        <p>
                          #{payment.id} {payment.method}
                        </p>
                        <p className="muted">Estado: {payment.status}</p>
                        <p className="muted">Monto: {formatArs(payment.amount)}</p>
                        <p className="muted">Ref: {payment.external_ref || "-"}</p>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
