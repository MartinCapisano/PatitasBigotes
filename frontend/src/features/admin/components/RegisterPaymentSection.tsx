import { useCallback } from "react";
import { useModalA11y } from "../../../lib/useModalA11y";
import type { AdminPayment } from "../../../services/admin-orders-api";
import type { AdminSearchUser } from "../../../services/admin-sales-api";
import { AdminUserSearchModal } from "./shared/AdminUserSearchModal";

export function RegisterPaymentSection(props: {
  selectedUser: AdminSearchUser | null;
  onClearSelectedUser: () => void;
  showUserSearch: boolean;
  openUserSearchModal: () => void;
  closeUserSearchModal: () => void;
  searchFirstName: string;
  setSearchFirstName: (value: string) => void;
  searchLastName: string;
  setSearchLastName: (value: string) => void;
  searchEmail: string;
  setSearchEmail: (value: string) => void;
  searchDni: string;
  setSearchDni: (value: string) => void;
  searchPhone: string;
  setSearchPhone: (value: string) => void;
  searchLoading: boolean;
  searchError: string;
  searchResults: AdminSearchUser[];
  pendingSelectedUser: AdminSearchUser | null;
  onTogglePendingUser: (user: AdminSearchUser, checked: boolean) => void;
  onConfirmPendingUser: () => void;
  pendingPayments: AdminPayment[];
  pendingPaymentsLoading: boolean;
  pendingPaymentsError: string;
  selectedPaymentId: number | null;
  setSelectedPaymentId: (value: number) => void;
  selectedPayment: AdminPayment | null;
  selectedMethod: "cash" | "bank_transfer" | null;
  paidAmount: string;
  setPaidAmount: (value: string) => void;
  changeAmount: string;
  setChangeAmount: (value: string) => void;
  paymentRef: string;
  setPaymentRef: (value: string) => void;
  saving: boolean;
  error: string;
  success: string;
  showConfirmModal: boolean;
  setShowConfirmModal: (value: boolean) => void;
  onOpenConfirm: () => void;
  onConfirmPayment: () => Promise<void>;
  formatArs: (cents: number | null) => string;
}) {
  const {
    selectedUser,
    onClearSelectedUser,
    showUserSearch,
    openUserSearchModal,
    closeUserSearchModal,
    searchFirstName,
    setSearchFirstName,
    searchLastName,
    setSearchLastName,
    searchEmail,
    setSearchEmail,
    searchDni,
    setSearchDni,
    searchPhone,
    setSearchPhone,
    searchLoading,
    searchError,
    searchResults,
    pendingSelectedUser,
    onTogglePendingUser,
    onConfirmPendingUser,
    pendingPayments,
    pendingPaymentsLoading,
    pendingPaymentsError,
    selectedPaymentId,
    setSelectedPaymentId,
    selectedPayment,
    selectedMethod,
    paidAmount,
    setPaidAmount,
    changeAmount,
    setChangeAmount,
    paymentRef,
    setPaymentRef,
    saving,
    error,
    success,
    showConfirmModal,
    setShowConfirmModal,
    onOpenConfirm,
    onConfirmPayment,
    formatArs
  } = props;

  const onCloseConfirmModal = useCallback(() => setShowConfirmModal(false), [setShowConfirmModal]);
  const confirmModalRef = useModalA11y<HTMLDivElement>(showConfirmModal, onCloseConfirmModal);

  return (
    <article className="card admin-orders-section">
      <h2>Registrar pago</h2>
      <p className="muted">Selecciona cliente, elige una orden submitted y confirma el pago con doble chequeo.</p>

      <section className="admin-sales-block">
        <h3>Cliente</h3>
        <div className="admin-inline-actions">
          <button className="btn btn-small btn-ghost" type="button" onClick={openUserSearchModal}>
            Buscar usuario existente
          </button>
          {selectedUser && (
            <button className="btn btn-small btn-ghost" type="button" onClick={onClearSelectedUser}>
              Quitar usuario seleccionado
            </button>
          )}
        </div>
        {selectedUser ? (
          <p className="muted">
            Seleccionado: #{selectedUser.id} - {selectedUser.first_name} {selectedUser.last_name} ({selectedUser.email})
          </p>
        ) : (
          <p className="muted">Todavia no seleccionaste un usuario.</p>
        )}
      </section>

      <section className="admin-sales-block">
        <h3>Pagos manuales pendientes del cliente</h3>
        {pendingPaymentsLoading ? (
          <p className="muted">Cargando pagos pendientes...</p>
        ) : pendingPayments.length === 0 ? (
          <p className="muted">No hay pagos manuales pendientes para este cliente.</p>
        ) : (
          <div className="admin-scroll-list admin-search-results-list">
            {pendingPayments.map((payment) => (
              <label className="admin-user-search-row" key={payment.id}>
                <span className="admin-discount-product-check">
                  <input
                    type="checkbox"
                    checked={selectedPaymentId === payment.id}
                    onChange={(event) => {
                      if (event.target.checked) setSelectedPaymentId(payment.id);
                    }}
                  />
                  <span>Pago #{payment.id} | Orden #{payment.order_id}</span>
                </span>
                <span className="muted">Metodo: {payment.method === "cash" ? "Efectivo" : "Transferencia"}</span>
                <span className="muted">Estado: {payment.status}</span>
                <span className="muted">Monto pendiente: {formatArs(payment.amount)}</span>
              </label>
            ))}
          </div>
        )}
        {pendingPaymentsError && <p className="error">{pendingPaymentsError}</p>}
      </section>

      <section className="admin-sales-block">
        <h3>Pago</h3>
        <div className="admin-sales-fields">
          <label>
            Metodo
            <input
              className="input"
              value={
                selectedMethod === "cash"
                  ? "Efectivo"
                  : selectedMethod === "bank_transfer"
                  ? "Transferencia"
                  : ""
              }
              readOnly
              placeholder="Selecciona un pago pendiente"
            />
          </label>
          <label>
            Monto pagado (ARS)
            <input
              className="input"
              type="text"
              inputMode="numeric"
              placeholder="Ej: 19000 o 19.000"
              value={paidAmount}
              onChange={(e) => setPaidAmount(e.target.value)}
            />
          </label>
          {selectedMethod === "cash" && (
            <label>
              Vuelto (ARS)
              <input
                className="input"
                type="text"
                inputMode="numeric"
                placeholder="Ej: 500"
                value={changeAmount}
                onChange={(e) => setChangeAmount(e.target.value)}
              />
            </label>
          )}
          <label>
            Referencia de pago (nro. transaccion) {selectedMethod === "bank_transfer" ? "(obligatoria)" : "(opcional)"}
            <input className="input" value={paymentRef} onChange={(e) => setPaymentRef(e.target.value)} />
          </label>
        </div>
        <div className="admin-inline-actions">
          <button className="btn" type="button" onClick={onOpenConfirm} disabled={saving}>
            Confirmar pago
          </button>
        </div>
      </section>

      {error && <p className="error">{error}</p>}
      {success && <p className="success">{success}</p>}

      <AdminUserSearchModal
        title="Buscar usuario existente"
        show={showUserSearch}
        onClose={closeUserSearchModal}
        searchFirstName={searchFirstName}
        setSearchFirstName={setSearchFirstName}
        searchLastName={searchLastName}
        setSearchLastName={setSearchLastName}
        searchEmail={searchEmail}
        setSearchEmail={setSearchEmail}
        searchDni={searchDni}
        setSearchDni={setSearchDni}
        searchPhone={searchPhone}
        setSearchPhone={setSearchPhone}
        searchLoading={searchLoading}
        searchError={searchError}
        searchResults={searchResults}
        pendingSelectedUser={pendingSelectedUser}
        onTogglePendingUser={onTogglePendingUser}
        onConfirmPendingUser={onConfirmPendingUser}
      />

      {showConfirmModal && selectedPayment && selectedUser && selectedMethod && (
        <div
          className="admin-modal-overlay"
          role="dialog"
          aria-modal="true"
          ref={confirmModalRef}
          tabIndex={-1}
        >
          <div className="card admin-modal">
            <div className="admin-modal-header">
              <h3>Confirmar pago</h3>
              <button className="btn btn-small btn-ghost" type="button" onClick={() => setShowConfirmModal(false)}>
                X
              </button>
            </div>
            <p className="muted">
              Orden #{selectedPayment.order_id} | Cliente: {selectedUser.first_name} {selectedUser.last_name}
            </p>
            <p className="muted">Pago pendiente: #{selectedPayment.id}</p>
            <p className="muted">Total orden: {formatArs(selectedPayment.amount)}</p>
            <p className="muted">Metodo: {selectedMethod === "cash" ? "Efectivo" : "Transferencia"}</p>
            <p className="muted">Monto pagado: {paidAmount}</p>
            {selectedMethod === "cash" && <p className="muted">Vuelto: {changeAmount}</p>}
            {paymentRef.trim() && <p className="muted">Referencia: {paymentRef.trim()}</p>}
            <div className="admin-inline-actions">
              <button className="btn" type="button" onClick={() => void onConfirmPayment()} disabled={saving}>
                {saving ? "Guardando..." : "Confirmar definitivamente"}
              </button>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}
