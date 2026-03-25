import type { AdminSearchUser } from "../../../services/admin-sales-api";
import type { AdminProduct, AdminVariant } from "../../../services/admin-catalog-api";
import { AdminUserSearchModal } from "./shared/AdminUserSearchModal";

export function SalesSection(props: {
  firstName: string;
  setFirstName: (value: string) => void;
  lastName: string;
  setLastName: (value: string) => void;
  email: string;
  setEmail: (value: string) => void;
  phone: string;
  setPhone: (value: string) => void;
  dni: string;
  setDni: (value: string) => void;
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
  showProductSearch: boolean;
  openProductSearchModal: () => void;
  closeProductSearchModal: () => void;
  productSearchQuery: string;
  setProductSearchQuery: (value: string) => void;
  productSearchResults: AdminProduct[];
  pendingSelectedProductId: number | null;
  onTogglePendingProduct: (productId: number, checked: boolean) => void;
  onConfirmPendingProduct: () => void;
  selectedProduct: AdminProduct | null;
  onClearSelectedProduct: () => void;
  selectedProductVariants: AdminVariant[];
  newVariantId: string;
  setNewVariantId: (value: string) => void;
  newQuantity: string;
  setNewQuantity: (value: string) => void;
  items: Array<{
    variant_id: number;
    quantity: number;
    label: string;
    unit_price: number;
    line_total: number;
  }>;
  total: number;
  onAddItem: () => void;
  removeItem: (variantId: number) => void;
  registerPayment: boolean;
  setRegisterPayment: (value: boolean) => void;
  paymentMethod: "cash" | "bank_transfer";
  setPaymentMethod: (value: "cash" | "bank_transfer") => void;
  amountPaid: string;
  setAmountPaid: (value: string) => void;
  changeAmount: string;
  setChangeAmount: (value: string) => void;
  paymentRef: string;
  setPaymentRef: (value: string) => void;
  saving: boolean;
  error: string;
  success: string;
  onSubmit: (event: React.FormEvent) => Promise<void>;
  formatArs: (cents: number | null) => string;
}) {
  const {
    firstName,
    setFirstName,
    lastName,
    setLastName,
    email,
    setEmail,
    phone,
    setPhone,
    dni,
    setDni,
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
    showProductSearch,
    openProductSearchModal,
    closeProductSearchModal,
    productSearchQuery,
    setProductSearchQuery,
    productSearchResults,
    pendingSelectedProductId,
    onTogglePendingProduct,
    onConfirmPendingProduct,
    selectedProduct,
    onClearSelectedProduct,
    selectedProductVariants,
    newVariantId,
    setNewVariantId,
    newQuantity,
    setNewQuantity,
    items,
    total,
    onAddItem,
    removeItem,
    registerPayment,
    setRegisterPayment,
    paymentMethod,
    setPaymentMethod,
    amountPaid,
    setAmountPaid,
    changeAmount,
    setChangeAmount,
    paymentRef,
    setPaymentRef,
    saving,
    error,
    success,
    onSubmit,
    formatArs
  } = props;

  return (
    <article className="card admin-orders-section">
      <h2>Registrar venta</h2>
      <p className="muted">Carga una orden manual y opcionalmente registra el pago en el mismo flujo.</p>
      <form className="admin-sales-form" onSubmit={(event) => void onSubmit(event)}>
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
            <div className="card">
              <p><strong>Usuario seleccionado:</strong> #{selectedUser.id}</p>
              <p>{selectedUser.first_name} {selectedUser.last_name}</p>
              <p>Email: {selectedUser.email}</p>
              <p>Telefono: {selectedUser.phone || "-"}</p>
              <p>DNI: {selectedUser.dni || "-"}</p>
            </div>
          ) : (
            <div className="admin-sales-fields">
              <label>
                Nombre
                <input className="input" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
              </label>
              <label>
                Apellido
                <input className="input" value={lastName} onChange={(e) => setLastName(e.target.value)} />
              </label>
              <label>
                Email
                <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </label>
              <label>
                Telefono
                <input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} />
              </label>
              <label>
                DNI (opcional)
                <input className="input" value={dni} onChange={(e) => setDni(e.target.value)} />
              </label>
            </div>
          )}

        </section>

        <section className="admin-sales-block">
          <h3>Productos</h3>
          <div className="admin-inline-actions">
            <button className="btn btn-small btn-ghost" type="button" onClick={openProductSearchModal}>
              Buscar producto
            </button>
            {selectedProduct && (
              <button className="btn btn-small btn-ghost" type="button" onClick={onClearSelectedProduct}>
                Quitar producto seleccionado
              </button>
            )}
          </div>
          {selectedProduct && (
            <p className="muted">
              Producto seleccionado: #{selectedProduct.id} - {selectedProduct.name}
              {selectedProduct.category ? ` (${selectedProduct.category})` : ""}
            </p>
          )}
          <div className="admin-sales-fields">
            <label>
              Variante
              <select className="input" value={newVariantId} onChange={(e) => setNewVariantId(e.target.value)}>
                <option value="">Seleccionar variante</option>
                {selectedProductVariants.map((variant) => (
                  <option key={variant.id} value={String(variant.id)}>
                    {variant.sku} ({variant.size || "-"} / {variant.color || "-"}) - {formatArs(variant.price)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Cantidad
              <input className="input" type="number" min={1} value={newQuantity} onChange={(e) => setNewQuantity(e.target.value)} />
            </label>
          </div>
          <div className="admin-inline-actions">
            <button className="btn btn-small btn-ghost" type="button" onClick={onAddItem}>
              Agregar item
            </button>
          </div>
          {items.length > 0 && (
            <div className="admin-variants-grid">
              {items.map((item) => (
                <div className="admin-variant-row" key={item.variant_id}>
                  <p>{item.label}</p>
                  <p className="muted">Cantidad: {item.quantity}</p>
                  <p className="muted">Subtotal linea: {formatArs(item.line_total)}</p>
                  <div className="admin-product-actions">
                    <button className="btn btn-small btn-danger" type="button" onClick={() => removeItem(item.variant_id)}>
                      Quitar
                    </button>
                  </div>
                </div>
              ))}
              <p><strong>Total orden:</strong> {formatArs(total)}</p>
            </div>
          )}
        </section>

        <section className="admin-sales-block">
          <h3>Pago vinculado</h3>
          <label className="admin-discount-product-check">
            <input
              type="checkbox"
              checked={registerPayment}
              onChange={(e) => setRegisterPayment(e.target.checked)}
            />
            <span>Esta paga</span>
          </label>
          {registerPayment && (
            <div className="admin-sales-fields">
              <label>
                Metodo
                <select className="input" value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value as "cash" | "bank_transfer")}>
                  <option value="cash">Efectivo</option>
                  <option value="bank_transfer">Transferencia</option>
                </select>
              </label>
              <label>
                Monto pagado (centavos ARS)
                <input className="input" type="number" min={1} value={amountPaid} onChange={(e) => setAmountPaid(e.target.value)} />
              </label>
              {paymentMethod === "cash" && (
                <label>
                  Vuelto (centavos ARS)
                  <input className="input" type="number" min={0} value={changeAmount} onChange={(e) => setChangeAmount(e.target.value)} />
                </label>
              )}
              <label>
                Referencia de pago (nro. transaccion/comprobante) {paymentMethod === "bank_transfer" ? "(obligatoria)" : "(opcional)"}
                <input className="input" value={paymentRef} onChange={(e) => setPaymentRef(e.target.value)} />
              </label>
            </div>
          )}
        </section>

        <div className="admin-inline-actions">
          <button className="btn" type="submit" disabled={saving}>
            {saving ? "Guardando..." : "Registrar"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        {success && <p className="success">{success}</p>}
      </form>

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

      {showProductSearch && (
        <div className="admin-modal-overlay" role="dialog" aria-modal="true">
          <div className="card admin-modal">
            <div className="admin-modal-header">
              <h3>Buscar producto</h3>
              <button className="btn btn-small btn-ghost" type="button" onClick={closeProductSearchModal}>
                X
              </button>
            </div>
            <div className="admin-search-toolbar">
              <label className="admin-search-field">
                Producto o categoria
                <input
                  className="input"
                  value={productSearchQuery}
                  onChange={(event) => setProductSearchQuery(event.target.value)}
                  placeholder="Ej: alimento, juguetes..."
                />
              </label>
            </div>
            <div className="admin-scroll-list admin-search-results-list">
              {productSearchResults.map((product) => (
                <div className="admin-user-search-row" key={product.id}>
                  <label className="admin-discount-product-check">
                    <input
                      type="checkbox"
                      checked={pendingSelectedProductId === product.id}
                      onChange={(event) => onTogglePendingProduct(product.id, event.target.checked)}
                    />
                    <span>#{product.id} {product.name}</span>
                  </label>
                  <p className="muted">Categoria: {product.category || "-"}</p>
                  <p className="muted">Stock: {product.stock}</p>
                </div>
              ))}
            </div>
            <p className="muted">
              {pendingSelectedProductId
                ? `Seleccion temporal producto: #${pendingSelectedProductId}`
                : "Seleccion temporal producto: -"}
            </p>
            <div className="admin-inline-actions">
              <button className="btn btn-small" type="button" onClick={onConfirmPendingProduct} disabled={!pendingSelectedProductId}>
                Seleccionar
              </button>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}
