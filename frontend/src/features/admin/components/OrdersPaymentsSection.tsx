import type { AdminOrder, AdminPayment } from "../services";
import type { AdminSection } from "../types";

export function OrdersPaymentsSection(props: {
  adminSection: AdminSection;
  orderError: string;
  orderSuccess: string;
  showCreateManualOrderForm: boolean;
  setShowCreateManualOrderForm: (value: boolean | ((prev: boolean) => boolean)) => void;
  ordersFilter: "all" | "submitted" | "paid" | "cancelled";
  setOrdersFilter: (value: "all" | "submitted" | "paid" | "cancelled") => void;
  ordersSortBy: "created_at" | "id";
  setOrdersSortBy: (value: "created_at" | "id") => void;
  ordersSortDir: "desc" | "asc";
  setOrdersSortDir: (value: "desc" | "asc") => void;
  ordersShowAll: boolean;
  setOrdersShowAll: (value: boolean | ((prev: boolean) => boolean)) => void;
  manualEmail: string;
  setManualEmail: (value: string) => void;
  manualFirstName: string;
  setManualFirstName: (value: string) => void;
  manualLastName: string;
  setManualLastName: (value: string) => void;
  manualPhone: string;
  setManualPhone: (value: string) => void;
  manualVariantId: string;
  setManualVariantId: (value: string) => void;
  manualQuantity: string;
  setManualQuantity: (value: string) => void;
  variantOptions: Array<{ value: string; label: string }>;
  onAddManualItem: () => void;
  manualItems: Array<{ variant_id: number; quantity: number; label: string }>;
  removeManualItem: (variantId: number) => void;
  setManualItems: (value: Array<{ variant_id: number; quantity: number; label: string }>) => void;
  onCreateManualOrder: () => Promise<void>;
  ordersListLoading: boolean;
  ordersList: AdminOrder[];
  loadAdminOrder: (orderId: number) => Promise<void>;
  closeSelectedOrder: () => void;
  paymentsFilter: "all" | "pending" | "paid" | "cancelled" | "expired";
  setPaymentsFilter: (value: "all" | "pending" | "paid" | "cancelled" | "expired") => void;
  paymentsSortBy: "created_at" | "id";
  setPaymentsSortBy: (value: "created_at" | "id") => void;
  paymentsSortDir: "desc" | "asc";
  setPaymentsSortDir: (value: "desc" | "asc") => void;
  paymentsShowAll: boolean;
  setPaymentsShowAll: (value: boolean | ((prev: boolean) => boolean)) => void;
  showManualPaymentForm: boolean;
  setShowManualPaymentForm: (value: boolean | ((prev: boolean) => boolean)) => void;
  paymentsListLoading: boolean;
  paymentsList: AdminPayment[];
  selectedOrder: AdminOrder | null;
  orderPayments: AdminPayment[];
  manualPayRef: string;
  setManualPayRef: (value: string) => void;
  manualPayAmount: string;
  setManualPayAmount: (value: string) => void;
  onMarkOrderPaid: () => Promise<void>;
  formatArs: (cents: number | null) => string;
}) {
  const {
    adminSection,
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
    variantOptions,
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
    formatArs
  } = props;

  return (
    <article className="card admin-orders-section">
      <h2>{adminSection === "ordenes" ? "Admin Ordenes" : "Admin Pagos"}</h2>
      <p className="muted">
        {adminSection === "ordenes"
          ? "Ultimas ordenes, filtros por estado y orden por fecha o id."
          : "Ultimos pagos, filtros por estado y orden por fecha o id."}
      </p>
      {orderError && <p className="error">{orderError}</p>}
      {orderSuccess && <p className="success">{orderSuccess}</p>}

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

          {showCreateManualOrderForm && (
            <>
              <h3>Crear orden manual (submitted)</h3>
              <form
                className="admin-form-grid"
                onSubmit={(event) => {
                  event.preventDefault();
                  void onCreateManualOrder();
                }}
              >
                <label>
                  Email cliente
                  <input className="input" type="email" value={manualEmail} onChange={(e) => setManualEmail(e.target.value)} required />
                </label>
                <label>
                  Nombre
                  <input className="input" value={manualFirstName} onChange={(e) => setManualFirstName(e.target.value)} required />
                </label>
                <label>
                  Apellido
                  <input className="input" value={manualLastName} onChange={(e) => setManualLastName(e.target.value)} required />
                </label>
                <label>
                  Telefono
                  <input className="input" value={manualPhone} onChange={(e) => setManualPhone(e.target.value)} required />
                </label>
              </form>
              <div className="admin-form-grid">
                <label>
                  Variante
                  <select className="input" value={manualVariantId} onChange={(e) => setManualVariantId(e.target.value)}>
                    <option value="">Seleccionar variante</option>
                    {variantOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Cantidad
                  <input className="input" type="number" min={1} value={manualQuantity} onChange={(e) => setManualQuantity(e.target.value)} />
                </label>
                <div className="admin-inline-actions">
                  <button className="btn btn-small btn-ghost" type="button" onClick={onAddManualItem}>
                    Agregar item
                  </button>
                </div>
              </div>
              {manualItems.length > 0 && (
                <div className="admin-variants-grid">
                  {manualItems.map((item) => (
                    <div className="admin-variant-row" key={item.variant_id}>
                      <p>{item.label}</p>
                      <p className="muted">Cantidad: {item.quantity}</p>
                      <div className="admin-product-actions">
                        <button className="btn btn-small btn-danger" type="button" onClick={() => removeManualItem(item.variant_id)}>
                          Quitar
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="admin-inline-actions">
                <button className="btn" type="button" onClick={() => setManualItems([])}>
                  Limpiar items
                </button>
                <button className="btn" type="button" onClick={() => void onCreateManualOrder()}>
                  Crear orden manual
                </button>
              </div>
            </>
          )}

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
                    <button className="btn btn-small" type="button" onClick={() => void loadAdminOrder(order.id)}>
                      Ver detalle
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
                    <button className="btn btn-small" type="button" onClick={() => void loadAdminOrder(payment.order_id)}>
                      Ver orden #{payment.order_id}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {selectedOrder && (
        <div className="admin-modal-overlay" role="dialog" aria-modal="true">
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
                {showManualPaymentForm && (
                  <div className="admin-form-grid">
                    <label>
                      Ref pago manual
                      <input className="input" value={manualPayRef} onChange={(e) => setManualPayRef(e.target.value)} />
                    </label>
                    <label>
                      Monto (centavos ARS)
                      <input className="input" type="number" min={1} value={manualPayAmount} onChange={(e) => setManualPayAmount(e.target.value)} />
                    </label>
                    <div className="admin-inline-actions">
                      <button className="btn btn-small" type="button" onClick={() => void onMarkOrderPaid()}>
                        Marcar como pagada
                      </button>
                    </div>
                  </div>
                )}

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
