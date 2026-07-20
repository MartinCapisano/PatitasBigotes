import { memo, useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import type { AdminCategory, AdminProduct, AdminVariant } from "../services";
import type { VariantEditPayload } from "../hooks/useAdminCatalog";
import { useModalA11y } from "../../../lib/useModalA11y";
import { AdminActionsMenu } from "./shared/AdminActionsMenu";
import { AdminExpandButton } from "./shared/AdminExpandButton";
import { ConfirmModal } from "./shared/ConfirmModal";

const EMPTY_VARIANTS: AdminVariant[] = [];
const noopAsync = async () => {};

function ProductRowImpl(props: {
  product: AdminProduct;
  categories: AdminCategory[];
  variants: AdminVariant[];
  isExpanded: boolean;
  toggleProductExpanded: (productId: number) => void;
  isMenuOpen: boolean;
  setOpenProductMenuId: (value: number | null | ((prev: number | null) => number | null)) => void;
  onStartEdit: (product: AdminProduct) => void;
  onRequestDeleteProduct: (productId: number) => void;
  editingProductId: number | null;
  editName: string;
  setEditName: (value: string) => void;
  editCategory: string;
  setEditCategory: (value: string) => void;
  editDescription: string;
  setEditDescription: (value: string) => void;
  editImgUrl: string;
  setEditImgUrl: (value: string) => void;
  editActive: boolean;
  setEditActive: (value: boolean) => void;
  onSaveProductEdit: () => Promise<void>;
  setEditingProductId: (value: number | null) => void;
  editingVariantId: number | null;
  onStartVariantEdit: (variant: AdminVariant) => void;
  editVariantSku: string;
  setEditVariantSku: (value: string) => void;
  editVariantSize: string;
  setEditVariantSize: (value: string) => void;
  editVariantColor: string;
  setEditVariantColor: (value: string) => void;
  editVariantImgUrl: string;
  setEditVariantImgUrl: (value: string) => void;
  editVariantStock: string;
  setEditVariantStock: (value: string) => void;
  editVariantActive: boolean;
  setEditVariantActive: (value: boolean) => void;
  enableVariantPriceEdit: boolean;
  setEnableVariantPriceEdit: (value: boolean) => void;
  editVariantPrice: string;
  setEditVariantPrice: (value: string) => void;
  onSaveVariantEdit: (variant: AdminVariant) => Promise<void>;
  setEditingVariantId: (value: number | null) => void;
  formatArs: (cents: number | null) => string;
}) {
  const {
    product,
    categories,
    variants,
    isExpanded,
    toggleProductExpanded,
    isMenuOpen,
    setOpenProductMenuId,
    onStartEdit,
    onRequestDeleteProduct,
    editingProductId,
    editName,
    setEditName,
    editCategory,
    setEditCategory,
    editDescription,
    setEditDescription,
    editImgUrl,
    setEditImgUrl,
    editActive,
    setEditActive,
    onSaveProductEdit,
    setEditingProductId,
    editingVariantId,
    onStartVariantEdit,
    editVariantSku,
    setEditVariantSku,
    editVariantSize,
    setEditVariantSize,
    editVariantColor,
    setEditVariantColor,
    editVariantImgUrl,
    setEditVariantImgUrl,
    editVariantStock,
    setEditVariantStock,
    editVariantActive,
    setEditVariantActive,
    enableVariantPriceEdit,
    setEnableVariantPriceEdit,
    editVariantPrice,
    setEditVariantPrice,
    onSaveVariantEdit,
    setEditingVariantId,
    formatArs
  } = props;

  return (
    <article className="card" key={product.id}>
      <div className="admin-catalog-row">
        <AdminExpandButton
          expanded={isExpanded}
          onToggle={() => toggleProductExpanded(product.id)}
          expandLabel="Expandir producto"
          collapseLabel="Contraer producto"
        />
        <p>
          <strong>{product.name}</strong>
        </p>
        <p className="muted">{product.category || "-"}</p>
        <p className="muted">{formatArs(product.min_var_price)}</p>
        <p className="muted">{product.active ? "Activo" : "Inactivo"}</p>
        <AdminActionsMenu
          isOpen={isMenuOpen}
          onToggle={() => setOpenProductMenuId((prev) => (prev === product.id ? null : product.id))}
          label="Opciones de producto"
        >
          <button className="btn btn-small btn-ghost" type="button" onClick={() => onStartEdit(product)}>
            Editar
          </button>
          <button className="btn btn-small btn-danger" type="button" onClick={() => onRequestDeleteProduct(product.id)}>
            Eliminar
          </button>
        </AdminActionsMenu>
      </div>

      {editingProductId === product.id && (
        <div className="admin-edit-box">
          <h3>Editar producto</h3>
          <div className="admin-form-grid">
            <label>
              Nombre
              <input className="input" value={editName} onChange={(e) => setEditName(e.target.value)} />
            </label>
            <label>
              Categoria
              <select className="input" value={editCategory} onChange={(e) => setEditCategory(e.target.value)}>
                {categories.map((category) => (
                  <option key={category.id} value={category.name}>
                    {category.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Descripcion
              <input className="input" value={editDescription} onChange={(e) => setEditDescription(e.target.value)} />
            </label>
            <label>
              Img URL
              <input className="input" value={editImgUrl} onChange={(e) => setEditImgUrl(e.target.value)} />
            </label>
            <label>
              Activo
              <select className="input" value={editActive ? "1" : "0"} onChange={(e) => setEditActive(e.target.value === "1")}>
                <option value="1">Si</option>
                <option value="0">No</option>
              </select>
            </label>
          </div>
          <div className="admin-product-actions">
            <button className="btn btn-small" type="button" onClick={() => void onSaveProductEdit()}>
              Guardar cambios
            </button>
            <button className="btn btn-small btn-ghost" type="button" onClick={() => setEditingProductId(null)}>
              Cancelar
            </button>
          </div>
        </div>
      )}

      {isExpanded &&
        (variants.length === 0 ? (
          <p className="muted">Sin variantes.</p>
        ) : (
          <div className="admin-variants-grid">
            {variants.map((variant) => (
              <div className="admin-variant-row" key={variant.id}>
                <p>
                  <strong>{variant.sku}</strong> ({variant.size || "-"} / {variant.color || "-"})
                </p>
                <p className="muted">Precio: {formatArs(variant.price)}</p>
                <p className="muted">Stock: {variant.stock}</p>
                <div className="admin-product-actions">
                  <button className="btn btn-small btn-ghost" type="button" onClick={() => onStartVariantEdit(variant)}>
                    Editar variante
                  </button>
                </div>

                {editingVariantId === variant.id && (
                  <div className="admin-edit-box admin-variant-edit-box">
                    <h3>Editar variante</h3>
                    <div className="admin-form-grid">
                      <label>
                        SKU
                        <input className="input" value={editVariantSku} onChange={(e) => setEditVariantSku(e.target.value)} />
                      </label>
                      <label>
                        Talle
                        <input className="input" value={editVariantSize} onChange={(e) => setEditVariantSize(e.target.value)} />
                      </label>
                      <label>
                        Color
                        <input className="input" value={editVariantColor} onChange={(e) => setEditVariantColor(e.target.value)} />
                      </label>
                      <label>
                        Img URL
                        <input className="input" value={editVariantImgUrl} onChange={(e) => setEditVariantImgUrl(e.target.value)} />
                      </label>
                      <label>
                        Stock
                        <input className="input" type="number" min={0} value={editVariantStock} onChange={(e) => setEditVariantStock(e.target.value)} />
                      </label>
                      <label>
                        Activa
                        <select className="input" value={editVariantActive ? "1" : "0"} onChange={(e) => setEditVariantActive(e.target.value === "1")}>
                          <option value="1">Si</option>
                          <option value="0">No</option>
                        </select>
                      </label>
                    </div>

                    <div className="admin-variant-price-guard">
                      <label>
                        <input type="checkbox" checked={enableVariantPriceEdit} onChange={(e) => setEnableVariantPriceEdit(e.target.checked)} />
                        Habilitar cambio de precio (protegido)
                      </label>
                      {enableVariantPriceEdit && (
                        <label>
                          Precio (centavos ARS)
                          <input
                            className="input"
                            type="number"
                            min={0}
                            value={editVariantPrice}
                            onChange={(e) => setEditVariantPrice(e.target.value)}
                          />
                        </label>
                      )}
                    </div>

                    <div className="admin-product-actions">
                      <button className="btn btn-small" type="button" onClick={() => void onSaveVariantEdit(variant)}>
                        Guardar variante
                      </button>
                      <button className="btn btn-small btn-ghost" type="button" onClick={() => setEditingVariantId(null)}>
                        Cancelar
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
    </article>
  );
}

const ProductRow = memo(ProductRowImpl);

export function CatalogSection(props: {
  error: string;
  showCreateProductForm: boolean;
  setShowCreateProductForm: (value: boolean | ((prev: boolean) => boolean)) => void;
  onCreateProduct: (event: FormEvent) => Promise<void>;
  savingNew: boolean;
  newName: string;
  setNewName: (value: string) => void;
  newCategory: string;
  setNewCategory: (value: string) => void;
  categories: AdminCategory[];
  productsSorted: AdminProduct[];
  categoryNames: string[];
  catalogCategoryFilter: string;
  setCatalogCategoryFilter: (value: string) => void;
  catalogShowAll: boolean;
  setCatalogShowAll: (value: boolean | ((prev: boolean) => boolean)) => void;
  showAddStockModal: boolean;
  setShowAddStockModal: (value: boolean | ((prev: boolean) => boolean)) => void;
  stockProductId: string;
  setStockProductId: (value: string) => void;
  stockQuantity: string;
  setStockQuantity: (value: string) => void;
  addingStock: boolean;
  stockSuccessMessage: string;
  onOpenAddStockModal: () => void;
  onConfirmAddStock: (selectedVariantIds: number[]) => Promise<void>;
  showCreateCategoryForm: boolean;
  setShowCreateCategoryForm: (value: boolean | ((prev: boolean) => boolean)) => void;
  onCreateCategory: (event: FormEvent) => Promise<void>;
  showDeleteCategoryModal: boolean;
  setShowDeleteCategoryModal: (value: boolean | ((prev: boolean) => boolean)) => void;
  deleteCategoryId: string;
  setDeleteCategoryId: (value: string) => void;
  deletingCategory: boolean;
  deletableCategories: AdminCategory[];
  onOpenDeleteCategoryModal: () => void;
  onConfirmDeleteCategory: () => Promise<void>;
  newCategoryName: string;
  setNewCategoryName: (value: string) => void;
  creatingCategory: boolean;
  newDescription: string;
  setNewDescription: (value: string) => void;
  newImgUrl: string;
  setNewImgUrl: (value: string) => void;
  loading: boolean;
  visibleProducts: AdminProduct[];
  productsByCategory: Record<string, AdminProduct[]>;
  variantsByProduct: Record<number, AdminVariant[]>;
  expandedProducts: Record<number, boolean>;
  toggleProductExpanded: (productId: number) => void;
  openProductMenuId: number | null;
  setOpenProductMenuId: (value: number | null | ((prev: number | null) => number | null)) => void;
  onStartEdit: (product: AdminProduct) => void;
  productPendingDeleteId: number | null;
  deletingProduct: boolean;
  onRequestDeleteProduct: (productId: number) => void;
  onCancelDeleteProduct: () => void;
  onConfirmDeleteProduct: () => Promise<void>;
  editingProductId: number | null;
  editName: string;
  setEditName: (value: string) => void;
  editCategory: string;
  setEditCategory: (value: string) => void;
  editDescription: string;
  setEditDescription: (value: string) => void;
  editImgUrl: string;
  setEditImgUrl: (value: string) => void;
  editActive: boolean;
  setEditActive: (value: boolean) => void;
  onSaveProductEdit: () => Promise<void>;
  setEditingProductId: (value: number | null) => void;
  editingVariantId: number | null;
  onStartVariantEdit: (variant: AdminVariant) => void;
  editVariantSku: string;
  setEditVariantSku: (value: string) => void;
  editVariantSize: string;
  setEditVariantSize: (value: string) => void;
  editVariantColor: string;
  setEditVariantColor: (value: string) => void;
  editVariantImgUrl: string;
  setEditVariantImgUrl: (value: string) => void;
  editVariantStock: string;
  setEditVariantStock: (value: string) => void;
  editVariantActive: boolean;
  setEditVariantActive: (value: boolean) => void;
  enableVariantPriceEdit: boolean;
  setEnableVariantPriceEdit: (value: boolean) => void;
  editVariantPrice: string;
  setEditVariantPrice: (value: string) => void;
  onSaveVariantEdit: (variant: AdminVariant) => Promise<void>;
  setEditingVariantId: (value: number | null) => void;
  variantPriceConfirmation: { variant: AdminVariant; payload: VariantEditPayload } | null;
  savingVariant: boolean;
  onCancelVariantPriceChange: () => void;
  onConfirmVariantPriceChange: () => Promise<void>;
  formatArs: (cents: number | null) => string;
}) {
  const {
    error,
    showCreateProductForm,
    setShowCreateProductForm,
    onCreateProduct,
    savingNew,
    newName,
    setNewName,
    newCategory,
    setNewCategory,
    categories,
    productsSorted,
    categoryNames,
    catalogCategoryFilter,
    setCatalogCategoryFilter,
    catalogShowAll,
    setCatalogShowAll,
    showAddStockModal,
    setShowAddStockModal,
    stockProductId,
    setStockProductId,
    stockQuantity,
    setStockQuantity,
    addingStock,
    stockSuccessMessage,
    onOpenAddStockModal,
    onConfirmAddStock,
    showCreateCategoryForm,
    onCreateCategory,
    showDeleteCategoryModal,
    setShowDeleteCategoryModal,
    deleteCategoryId,
    setDeleteCategoryId,
    deletingCategory,
    deletableCategories,
    onConfirmDeleteCategory,
    newCategoryName,
    setNewCategoryName,
    creatingCategory,
    newDescription,
    setNewDescription,
    newImgUrl,
    setNewImgUrl,
    loading,
    visibleProducts,
    productsByCategory,
    variantsByProduct,
    expandedProducts,
    toggleProductExpanded,
    openProductMenuId,
    setOpenProductMenuId,
    onStartEdit,
    productPendingDeleteId,
    deletingProduct,
    onRequestDeleteProduct,
    onCancelDeleteProduct,
    onConfirmDeleteProduct,
    editingProductId,
    editName,
    setEditName,
    editCategory,
    setEditCategory,
    editDescription,
    setEditDescription,
    editImgUrl,
    setEditImgUrl,
    editActive,
    setEditActive,
    onSaveProductEdit,
    setEditingProductId,
    editingVariantId,
    onStartVariantEdit,
    editVariantSku,
    setEditVariantSku,
    editVariantSize,
    setEditVariantSize,
    editVariantColor,
    setEditVariantColor,
    editVariantImgUrl,
    setEditVariantImgUrl,
    editVariantStock,
    setEditVariantStock,
    editVariantActive,
    setEditVariantActive,
    enableVariantPriceEdit,
    setEnableVariantPriceEdit,
    editVariantPrice,
    setEditVariantPrice,
    onSaveVariantEdit,
    setEditingVariantId,
    variantPriceConfirmation,
    savingVariant,
    onCancelVariantPriceChange,
    onConfirmVariantPriceChange,
    formatArs
  } = props;
  const [stockSearch, setStockSearch] = useState("");
  const [selectedStockVariantIds, setSelectedStockVariantIds] = useState<number[]>([]);

  const onCloseAddStockModal = useCallback(() => setShowAddStockModal(false), [setShowAddStockModal]);
  const addStockModalRef = useModalA11y<HTMLDivElement>(showAddStockModal, onCloseAddStockModal);
  const onCloseDeleteCategoryModal = useCallback(
    () => setShowDeleteCategoryModal(false),
    [setShowDeleteCategoryModal]
  );
  const deleteCategoryModalRef = useModalA11y<HTMLDivElement>(showDeleteCategoryModal, onCloseDeleteCategoryModal);

  const groupedEntries =
    catalogCategoryFilter === "all"
      ? Object.entries(productsByCategory).sort(([a], [b]) => a.localeCompare(b))
      : [[catalogCategoryFilter, visibleProducts] as [string, AdminProduct[]]];

  const filteredStockProducts = useMemo(() => {
    const query = stockSearch.trim().toLowerCase();
    if (!query) return productsSorted;
    return productsSorted.filter((product) => product.name.toLowerCase().includes(query));
  }, [productsSorted, stockSearch]);

  const selectedStockProductVariantCount = useMemo(() => {
    const parsedProductId = Number.parseInt(stockProductId, 10);
    if (Number.isNaN(parsedProductId) || parsedProductId <= 0) return 0;
    const variants = variantsByProduct[parsedProductId] ?? [];
    return variants.length;
  }, [stockProductId, variantsByProduct]);

  const selectedStockProductVariants = useMemo(() => {
    const parsedProductId = Number.parseInt(stockProductId, 10);
    if (Number.isNaN(parsedProductId) || parsedProductId <= 0) return [] as AdminVariant[];
    return variantsByProduct[parsedProductId] ?? [];
  }, [stockProductId, variantsByProduct]);

  useEffect(() => {
    setSelectedStockVariantIds([]);
  }, [stockProductId, selectedStockProductVariantCount]);

  return (
    <>
      {error ? <p className="error">{error}</p> : null}
      <article className="card">
        <div className="admin-inline-actions">
          <button className="btn btn-small btn-ghost" type="button" onClick={() => setShowCreateProductForm((v) => !v)}>
            {showCreateProductForm ? "Ocultar crear producto" : "Agregar producto"}
          </button>
          <button className="btn btn-small btn-ghost" type="button" onClick={onOpenAddStockModal}>
            Agregar stock
          </button>
          <button className="btn btn-small" type="button" onClick={() => setCatalogShowAll((v) => !v)}>
            {catalogShowAll ? "Mostrar primeros 200" : "Mostrar todo el catálogo"}
          </button>
        </div>

        <div className="admin-category-nav">
          <button
            type="button"
            className={`menu-tab ${catalogCategoryFilter === "all" ? "menu-tab-active" : ""}`}
            onClick={() => setCatalogCategoryFilter("all")}
          >
            Todas
          </button>
          {categoryNames.map((name) => (
            <button
              key={name}
              type="button"
              className={`menu-tab ${catalogCategoryFilter === name ? "menu-tab-active" : ""}`}
              onClick={() => setCatalogCategoryFilter(name)}
            >
              {name}
            </button>
          ))}
        </div>

        {showCreateCategoryForm ? (
          <form className="admin-form-grid" onSubmit={(event) => void onCreateCategory(event)}>
            <label>
              Nueva categoria
              <input className="input" value={newCategoryName} onChange={(event) => setNewCategoryName(event.target.value)} required />
            </label>
            <div>
              <button className="btn" type="submit" disabled={creatingCategory}>
                {creatingCategory ? "Guardando..." : "Guardar categoria"}
              </button>
            </div>
          </form>
        ) : null}

        {showCreateProductForm ? (
          <>
            <h2>Agregar producto</h2>
            <form className="admin-form-grid" onSubmit={(event) => void onCreateProduct(event)}>
              <label>
                Nombre
                <input className="input" value={newName} onChange={(event) => setNewName(event.target.value)} required />
              </label>
              <label>
                Categoria
                <select className="input" value={newCategory} onChange={(event) => setNewCategory(event.target.value)} required>
                  {categories.map((category) => (
                    <option key={category.id} value={category.name}>
                      {category.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Descripcion
                <input className="input" value={newDescription} onChange={(event) => setNewDescription(event.target.value)} />
              </label>
              <label>
                Img URL
                <input className="input" value={newImgUrl} onChange={(event) => setNewImgUrl(event.target.value)} />
              </label>
              <div>
                <button className="btn" type="submit" disabled={savingNew}>
                  {savingNew ? "Guardando..." : "Agregar producto"}
                </button>
              </div>
            </form>
          </>
        ) : null}
      </article>

      {loading ? (
        <p>Cargando catalogo...</p>
      ) : groupedEntries.length === 0 ? (
        <p className="muted">No hay productos para la categoria seleccionada.</p>
      ) : (
        <div className="admin-products-list">
          {groupedEntries.map(([category, products]) => (
            <section key={category} className="admin-catalog-category-block">
              {catalogCategoryFilter === "all" ? <h3 className="admin-catalog-category-title">{category}</h3> : null}
              <div className="admin-catalog-header">
                <p />
                <p>Producto</p>
                <p>Categoria</p>
                <p>Precio base</p>
                <p>Estado</p>
                <p>Acciones</p>
              </div>
              {products.map((product) => {
                const productVariants = variantsByProduct[product.id] ?? EMPTY_VARIANTS;
                const isEditingThisProduct = editingProductId === product.id;
                const isEditingVariantHere = productVariants.some((variant) => variant.id === editingVariantId);
                return (
                  <ProductRow
                    key={product.id}
                    product={product}
                    categories={categories}
                    variants={productVariants}
                    isExpanded={Boolean(expandedProducts[product.id])}
                    toggleProductExpanded={toggleProductExpanded}
                    isMenuOpen={openProductMenuId === product.id}
                    setOpenProductMenuId={setOpenProductMenuId}
                    onStartEdit={onStartEdit}
                    onRequestDeleteProduct={onRequestDeleteProduct}
                    editingProductId={editingProductId}
                    editName={isEditingThisProduct ? editName : ""}
                    setEditName={setEditName}
                    editCategory={isEditingThisProduct ? editCategory : ""}
                    setEditCategory={setEditCategory}
                    editDescription={isEditingThisProduct ? editDescription : ""}
                    setEditDescription={setEditDescription}
                    editImgUrl={isEditingThisProduct ? editImgUrl : ""}
                    setEditImgUrl={setEditImgUrl}
                    editActive={isEditingThisProduct ? editActive : false}
                    setEditActive={setEditActive}
                    onSaveProductEdit={isEditingThisProduct ? onSaveProductEdit : noopAsync}
                    setEditingProductId={setEditingProductId}
                    editingVariantId={editingVariantId}
                    onStartVariantEdit={onStartVariantEdit}
                    editVariantSku={isEditingVariantHere ? editVariantSku : ""}
                    setEditVariantSku={setEditVariantSku}
                    editVariantSize={isEditingVariantHere ? editVariantSize : ""}
                    setEditVariantSize={setEditVariantSize}
                    editVariantColor={isEditingVariantHere ? editVariantColor : ""}
                    setEditVariantColor={setEditVariantColor}
                    editVariantImgUrl={isEditingVariantHere ? editVariantImgUrl : ""}
                    setEditVariantImgUrl={setEditVariantImgUrl}
                    editVariantStock={isEditingVariantHere ? editVariantStock : ""}
                    setEditVariantStock={setEditVariantStock}
                    editVariantActive={isEditingVariantHere ? editVariantActive : false}
                    setEditVariantActive={setEditVariantActive}
                    enableVariantPriceEdit={isEditingVariantHere ? enableVariantPriceEdit : false}
                    setEnableVariantPriceEdit={setEnableVariantPriceEdit}
                    editVariantPrice={isEditingVariantHere ? editVariantPrice : ""}
                    setEditVariantPrice={setEditVariantPrice}
                    onSaveVariantEdit={isEditingVariantHere ? onSaveVariantEdit : noopAsync}
                    setEditingVariantId={setEditingVariantId}
                    formatArs={formatArs}
                  />
                );
              })}
            </section>
          ))}
        </div>
      )}

      {showAddStockModal ? (
        <div className="admin-modal-overlay" role="dialog" aria-modal="true" ref={addStockModalRef} tabIndex={-1}>
          <div className="card admin-modal">
            <div className="admin-modal-header">
              <h3>Agregar stock</h3>
              <button className="btn btn-small btn-ghost" type="button" onClick={() => setShowAddStockModal(false)}>
                Cerrar
              </button>
            </div>
            <div className="admin-form-grid">
              <label>
                Buscar producto por nombre
                <input
                  className="input"
                  value={stockSearch}
                  onChange={(event) => setStockSearch(event.target.value)}
                  placeholder="Ej: alimento, collar, shampoo..."
                />
              </label>
              <label>
                Producto
                <select className="input" value={stockProductId} onChange={(event) => setStockProductId(event.target.value)}>
                  <option value="">Seleccionar producto</option>
                  {filteredStockProducts.map((product) => (
                    <option key={product.id} value={String(product.id)}>
                      {product.name} ({product.category || "Sin categoria"})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Cantidad a agregar
                <input
                  className="input"
                  type="number"
                  min={1}
                  value={stockQuantity}
                  onChange={(event) => setStockQuantity(event.target.value)}
                />
              </label>
            </div>
            {selectedStockProductVariants.length > 0 ? (
              <div className="admin-variants-grid">
                <p className="muted">Selecciona variantes a actualizar:</p>
                {selectedStockProductVariants.map((variant) => {
                  const checked = selectedStockVariantIds.includes(Number(variant.id));
                  return (
                    <label key={variant.id} className="admin-discount-variant-check">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(event) => {
                          const currentId = Number(variant.id);
                          if (event.target.checked) {
                            setSelectedStockVariantIds((prev) => [...prev, currentId]);
                          } else {
                            setSelectedStockVariantIds((prev) => prev.filter((id) => id !== currentId));
                          }
                        }}
                      />
                      <span>
                        {variant.sku} ({variant.size || "-"} / {variant.color || "-"}) | Stock actual: {variant.stock}
                      </span>
                    </label>
                  );
                })}
              </div>
            ) : null}
            <p className="muted">
              Se sumara esa cantidad a las variantes seleccionadas. Variantes disponibles: {selectedStockProductVariantCount}. Seleccionadas:{" "}
              {selectedStockVariantIds.length}.
            </p>
            {stockSuccessMessage ? <p className="success">{stockSuccessMessage}</p> : null}
            <div className="admin-product-actions">
              <button
                className="btn"
                type="button"
                onClick={() => void onConfirmAddStock(selectedStockVariantIds)}
                disabled={
                  addingStock ||
                  !stockProductId ||
                  selectedStockProductVariantCount <= 0 ||
                  selectedStockVariantIds.length <= 0
                }
              >
                {addingStock ? "Actualizando..." : "Confirmar"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {showDeleteCategoryModal ? (
        <div
          className="admin-modal-overlay"
          role="dialog"
          aria-modal="true"
          ref={deleteCategoryModalRef}
          tabIndex={-1}
        >
          <div className="card admin-modal">
            <div className="admin-modal-header">
              <h3>Eliminar categoria</h3>
              <button className="btn btn-small btn-ghost" type="button" onClick={() => setShowDeleteCategoryModal(false)}>
                Cerrar
              </button>
            </div>
            {deletableCategories.length === 0 ? (
              <p className="muted">No hay categorias eliminables. Todas tienen productos asociados.</p>
            ) : (
              <>
                <label>
                  Categoria (solo sin productos)
                  <select className="input" value={deleteCategoryId} onChange={(event) => setDeleteCategoryId(event.target.value)}>
                    {deletableCategories.map((category) => (
                      <option key={category.id} value={String(category.id)}>
                        {category.name}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="admin-product-actions">
                  <button className="btn btn-danger" type="button" onClick={() => void onConfirmDeleteCategory()} disabled={deletingCategory}>
                    {deletingCategory ? "Eliminando..." : "Eliminar categoria"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      ) : null}

      {productPendingDeleteId !== null ? (
        <ConfirmModal
          title="Eliminar producto"
          message="Esta accion es irreversible. Confirma para eliminar el producto."
          confirmLabel="Eliminar producto"
          busyLabel="Eliminando..."
          danger
          busy={deletingProduct}
          onConfirm={() => void onConfirmDeleteProduct()}
          onCancel={onCancelDeleteProduct}
        />
      ) : null}

      {variantPriceConfirmation ? (
        <ConfirmModal
          title="Cambiar precio de variante"
          message={`Vas a cambiar el precio de "${variantPriceConfirmation.variant.sku}" a ${formatArs(
            variantPriceConfirmation.payload.price ?? 0
          )}. Confirma para continuar.`}
          confirmLabel="Confirmar cambio"
          busyLabel="Guardando..."
          busy={savingVariant}
          onConfirm={() => void onConfirmVariantPriceChange()}
          onCancel={onCancelVariantPriceChange}
        />
      ) : null}
    </>
  );
}
