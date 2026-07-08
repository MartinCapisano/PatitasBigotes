import { useMemo, useState } from "react";
import type { AdminCategory, AdminProduct, AdminVariant, AdminDiscount } from "../services";
import { AdminActionsMenu } from "./shared/AdminActionsMenu";
import { AdminExpandButton } from "./shared/AdminExpandButton";
import { ConfirmModal } from "./shared/ConfirmModal";

export function DiscountsSection(props: {
  discountsError: string;
  discountsLoading: boolean;
  discounts: AdminDiscount[];
  showCreateDiscountForm: boolean;
  setShowCreateDiscountForm: (value: boolean | ((prev: boolean) => boolean)) => void;
  loadDiscounts: () => Promise<void>;
  newDiscountName: string;
  setNewDiscountName: (value: string) => void;
  newDiscountType: "percent" | "fixed";
  setNewDiscountType: (value: "percent" | "fixed") => void;
  newDiscountValue: string;
  setNewDiscountValue: (value: string) => void;
  newDiscountTarget: "all" | "category" | "products";
  setNewDiscountTarget: (value: "all" | "category" | "products") => void;
  newDiscountCategoryId: string;
  setNewDiscountCategoryId: (value: string) => void;
  categories: AdminCategory[];
  newDiscountActive: boolean;
  setNewDiscountActive: (value: boolean) => void;
  showDiscountProductPicker: boolean;
  setShowDiscountProductPicker: (value: boolean | ((prev: boolean) => boolean)) => void;
  selectedDiscountProductCount: number;
  selectedDiscountVariantCount: number;
  productsSorted: AdminProduct[];
  variantsByProduct: Record<number, AdminVariant[]>;
  discountPickerExpandedProducts: Record<number, boolean>;
  toggleDiscountPickerProductExpanded: (productId: number) => void;
  selectedDiscountProductIds: Record<number, boolean>;
  selectedDiscountVariantIds: Record<number, boolean>;
  toggleDiscountProductSelection: (productId: number, checked: boolean) => void;
  toggleDiscountVariantSelection: (productId: number, variantId: number, checked: boolean) => void;
  onCreateDiscount: () => Promise<void>;
  onToggleDiscountActive: (discount: AdminDiscount) => Promise<void>;
  discountPendingDeleteId: number | null;
  deletingDiscount: boolean;
  onRequestDeleteDiscount: (discountId: number) => void;
  onCancelDeleteDiscount: () => void;
  onConfirmDeleteDiscount: () => Promise<void>;
  formatArs: (cents: number | null) => string;
}) {
  const {
    discountsError,
    discountsLoading,
    discounts,
    showCreateDiscountForm,
    setShowCreateDiscountForm,
    loadDiscounts,
    newDiscountName,
    setNewDiscountName,
    newDiscountType,
    setNewDiscountType,
    newDiscountValue,
    setNewDiscountValue,
    newDiscountTarget,
    setNewDiscountTarget,
    newDiscountCategoryId,
    setNewDiscountCategoryId,
    categories,
    newDiscountActive,
    setNewDiscountActive,
    showDiscountProductPicker,
    setShowDiscountProductPicker,
    selectedDiscountProductCount,
    selectedDiscountVariantCount,
    productsSorted,
    variantsByProduct,
    discountPickerExpandedProducts,
    toggleDiscountPickerProductExpanded,
    selectedDiscountProductIds,
    selectedDiscountVariantIds,
    toggleDiscountProductSelection,
    toggleDiscountVariantSelection,
    onCreateDiscount,
    onToggleDiscountActive,
    discountPendingDeleteId,
    deletingDiscount,
    onRequestDeleteDiscount,
    onCancelDeleteDiscount,
    onConfirmDeleteDiscount,
    formatArs
  } = props;
  const [expandedDiscounts, setExpandedDiscounts] = useState<Record<number, boolean>>({});
  const [openDiscountMenuId, setOpenDiscountMenuId] = useState<number | null>(null);

  const discountPendingDeleteName = useMemo(
    () => discounts.find((discount) => discount.id === discountPendingDeleteId)?.name ?? "",
    [discounts, discountPendingDeleteId]
  );

  function toggleDiscountExpanded(discountId: number) {
    setExpandedDiscounts((prev) => ({ ...prev, [discountId]: !prev[discountId] }));
  }

  function formatDiscountValue(discount: AdminDiscount): string {
    return discount.type === "percent" ? `${discount.value}%` : formatArs(discount.value);
  }

  function formatDiscountScope(discount: AdminDiscount): string {
    if (discount.scope === "all") return "Todo el catalogo";
    if (discount.scope === "category") return "Categoria";
    if (discount.scope === "product") return "Producto";
    return "Lista de productos";
  }

  function resolveCategoryName(categoryId: number | null): string {
    if (categoryId == null) return "-";
    return categories.find((category) => category.id === categoryId)?.name || `#${categoryId}`;
  }

  return (
    <>
    <article className="card admin-orders-section">
      <h2>Admin Descuentos</h2>
      <div className="admin-inline-actions">
        <button className="btn btn-small btn-ghost" type="button" onClick={() => setShowCreateDiscountForm((v) => !v)}>
          {showCreateDiscountForm ? "Ocultar crear descuento" : "Crear descuento"}
        </button>
        <button className="btn btn-small" type="button" onClick={() => void loadDiscounts()}>
          Refrescar
        </button>
      </div>
      {discountsError && <p className="error">{discountsError}</p>}

      {showCreateDiscountForm && (
        <>
          <h3>Nuevo descuento</h3>
          <div className="admin-form-grid">
            <label>
              Nombre
              <input className="input" value={newDiscountName} onChange={(e) => setNewDiscountName(e.target.value)} />
            </label>
            <label>
              Tipo
              <select className="input" value={newDiscountType} onChange={(e) => setNewDiscountType(e.target.value as "percent" | "fixed")}>
                <option value="percent">Percent</option>
                <option value="fixed">Fixed</option>
              </select>
            </label>
            <label>
              Valor
              <input className="input" type="number" min={1} value={newDiscountValue} onChange={(e) => setNewDiscountValue(e.target.value)} />
            </label>
            <label>
              Alcance inicial
              <select className="input" value={newDiscountTarget} onChange={(e) => setNewDiscountTarget(e.target.value as "all" | "category" | "products")}>
                <option value="all">Todo el catalogo</option>
                <option value="category">Categoria</option>
                <option value="products">Producto(s)</option>
              </select>
            </label>
            {newDiscountTarget === "category" && (
              <label>
                Categoria
                <select className="input" value={newDiscountCategoryId} onChange={(e) => setNewDiscountCategoryId(e.target.value)}>
                  <option value="">Seleccionar categoria...</option>
                  {categories.map((category) => (
                    <option key={category.id} value={String(category.id)}>
                      {category.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              Activo
              <select className="input" value={newDiscountActive ? "1" : "0"} onChange={(e) => setNewDiscountActive(e.target.value === "1")}>
                <option value="1">Si</option>
                <option value="0">No</option>
              </select>
            </label>
          </div>
          {newDiscountTarget === "products" && (
            <div className="admin-discount-picker-wrap">
              <div className="admin-inline-actions">
                <button className="btn btn-small btn-ghost" type="button" onClick={() => setShowDiscountProductPicker((prev) => !prev)}>
                  {showDiscountProductPicker ? "Ocultar selector" : "Seleccionar productos"}
                </button>
              </div>
              <p className="muted">
                Seleccionados: {selectedDiscountProductCount} productos, {selectedDiscountVariantCount} variantes.
              </p>
              {showDiscountProductPicker && (
                <div className="admin-discount-picker-list">
                  {productsSorted.map((product) => {
                    const variants = variantsByProduct[product.id] ?? [];
                    return (
                      <article className="card" key={`discount-picker-${product.id}`}>
                        <div className="admin-product-head">
                          <button
                            className="admin-expand-btn"
                            type="button"
                            onClick={() => toggleDiscountPickerProductExpanded(product.id)}
                            aria-label={discountPickerExpandedProducts[product.id] ? "Contraer producto" : "Expandir producto"}
                          >
                            {discountPickerExpandedProducts[product.id] ? "▾" : "▸"}
                          </button>
                          <label className="admin-discount-product-check">
                            <input
                              type="checkbox"
                              checked={!!selectedDiscountProductIds[product.id]}
                              onChange={(event) => toggleDiscountProductSelection(product.id, event.target.checked)}
                            />
                            <span>
                              <strong>{product.name}</strong>
                              <span className="muted"> #{product.id}</span>
                            </span>
                          </label>
                        </div>
                        {discountPickerExpandedProducts[product.id] && (
                          <div className="admin-variants-grid">
                            {variants.length === 0 ? (
                              <p className="muted">Sin variantes.</p>
                            ) : (
                              variants.map((variant) => (
                                <label className="admin-discount-variant-check" key={`discount-picker-variant-${variant.id}`}>
                                  <input
                                    type="checkbox"
                                    checked={!!selectedDiscountVariantIds[variant.id]}
                                    onChange={(event) => toggleDiscountVariantSelection(product.id, variant.id, event.target.checked)}
                                  />
                                  <span>
                                    {variant.sku} | Talle: {variant.size || "-"} | Color: {variant.color || "-"} | {formatArs(variant.price)}
                                  </span>
                                </label>
                              ))
                            )}
                          </div>
                        )}
                      </article>
                    );
                  })}
                </div>
              )}
            </div>
          )}
          <div className="admin-inline-actions">
            <button className="btn btn-small" type="button" onClick={() => void onCreateDiscount()}>
              Guardar descuento
            </button>
          </div>
        </>
      )}

      <h3>Listado</h3>
      {discountsLoading ? (
        <p>Cargando descuentos...</p>
      ) : discounts.length === 0 ? (
        <p className="muted">No hay descuentos configurados.</p>
      ) : (
        <div className="admin-products-list">
          <div className="admin-catalog-header">
            <p />
            <p>Descuento</p>
            <p>Tipo / valor</p>
            <p>Alcance</p>
            <p>Estado</p>
            <p>Acciones</p>
          </div>
          {discounts.map((discount) => (
            <article className="card" key={discount.id}>
              <div className="admin-catalog-row">
                <AdminExpandButton
                  expanded={!!expandedDiscounts[discount.id]}
                  onToggle={() => toggleDiscountExpanded(discount.id)}
                  expandLabel="Expandir descuento"
                  collapseLabel="Contraer descuento"
                />
                <p>
                  <strong>{discount.name}</strong>
                </p>
                <p className="muted">
                  {discount.type === "percent" ? "Porcentaje" : "Monto fijo"} | {formatDiscountValue(discount)}
                </p>
                <p className="muted">{formatDiscountScope(discount)}</p>
                <p className="muted">{discount.is_active ? "Activo" : "Inactivo"}</p>
                <AdminActionsMenu
                  isOpen={openDiscountMenuId === discount.id}
                  onToggle={() => setOpenDiscountMenuId((prev) => (prev === discount.id ? null : discount.id))}
                  label="Opciones de descuento"
                >
                  <button className="btn btn-small btn-ghost" type="button" onClick={() => void onToggleDiscountActive(discount)}>
                    {discount.is_active ? "Desactivar" : "Activar"}
                  </button>
                  <button className="btn btn-small btn-danger" type="button" onClick={() => onRequestDeleteDiscount(discount.id)}>
                    Eliminar
                  </button>
                </AdminActionsMenu>
              </div>

              {expandedDiscounts[discount.id] ? (
                <div className="admin-variants-grid">
                  <div className="admin-variant-row">
                    <p><strong>ID:</strong> #{discount.id}</p>
                    <p className="muted"><strong>Categoria:</strong> {resolveCategoryName(discount.category_id)}</p>
                    <p className="muted"><strong>Producto directo:</strong> {discount.product_id != null ? `#${discount.product_id}` : "-"}</p>
                    <p className="muted"><strong>Productos vinculados:</strong> {discount.product_ids.length}</p>
                    <p className="muted"><strong>Inicio:</strong> {discount.starts_at ? new Date(discount.starts_at).toLocaleString() : "-"}</p>
                    <p className="muted"><strong>Fin:</strong> {discount.ends_at ? new Date(discount.ends_at).toLocaleString() : "-"}</p>
                  </div>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </article>

    {discountPendingDeleteId !== null ? (
      <ConfirmModal
        title="Eliminar descuento"
        message={`Confirma para eliminar el descuento "${discountPendingDeleteName}".`}
        confirmLabel="Eliminar descuento"
        busyLabel="Eliminando..."
        danger
        busy={deletingDiscount}
        onConfirm={() => void onConfirmDeleteDiscount()}
        onCancel={onCancelDeleteDiscount}
      />
    ) : null}
    </>
  );
}
