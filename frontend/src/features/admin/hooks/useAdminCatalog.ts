import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  type AdminCategory,
  type AdminCatalog,
  type AdminProduct,
  type AdminVariant,
  createAdminProduct,
  deleteAdminProduct,
  getAdminCatalog,
  patchAdminProduct,
  patchAdminVariant
} from "../../../services/admin-catalog-api";
import type { AdminSection } from "../types";
import { useAdminCategories } from "./useAdminCategories";

const CATALOG_DEPENDENT_SECTIONS: AdminSection[] = ["categorias", "catalogo", "descuentos", "registrar_venta"];

function normalizeVariantsByProduct(
  payload: Record<string, AdminVariant[]>
): Record<number, AdminVariant[]> {
  const next: Record<number, AdminVariant[]> = {};
  for (const [productId, variants] of Object.entries(payload)) {
    const numericId = Number(productId);
    if (!Number.isFinite(numericId)) continue;
    next[numericId] = [...variants].sort((a, b) => a.id - b.id);
  }
  return next;
}

export type VariantEditPayload = {
  sku: string;
  size: string | null;
  color: string | null;
  img_url: string | null;
  stock: number;
  active: boolean;
  price?: number;
};

function deriveProductFromVariants(product: AdminProduct, variants: AdminVariant[]): AdminProduct {
  const activeVariants = variants.filter((variant) => Boolean(variant.active));
  const totalStock = activeVariants.reduce((sum, variant) => sum + Number(variant.stock ?? 0), 0);
  const minVarPrice =
    activeVariants.length > 0
      ? Math.min(...activeVariants.map((variant) => Number(variant.price ?? 0)))
      : null;
  return {
    ...product,
    stock: totalStock,
    active: activeVariants.length > 0,
    min_var_price: minVarPrice
  };
}

export function useAdminCatalog(adminSection: AdminSection) {
  const [products, setProducts] = useState<AdminProduct[]>([]);
  const [categories, setCategories] = useState<AdminCategory[]>([]);
  const [variantsByProduct, setVariantsByProduct] = useState<Record<number, AdminVariant[]>>({});
  const [expandedProducts, setExpandedProducts] = useState<Record<number, boolean>>({});
  const [openProductMenuId, setOpenProductMenuId] = useState<number | null>(null);
  const [showCreateProductForm, setShowCreateProductForm] = useState(false);
  const [editingProductId, setEditingProductId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editImgUrl, setEditImgUrl] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [editingVariantId, setEditingVariantId] = useState<number | null>(null);
  const [editVariantSku, setEditVariantSku] = useState("");
  const [editVariantSize, setEditVariantSize] = useState("");
  const [editVariantColor, setEditVariantColor] = useState("");
  const [editVariantImgUrl, setEditVariantImgUrl] = useState("");
  const [editVariantStock, setEditVariantStock] = useState("0");
  const [editVariantActive, setEditVariantActive] = useState(true);
  const [enableVariantPriceEdit, setEnableVariantPriceEdit] = useState(false);
  const [editVariantPrice, setEditVariantPrice] = useState("0");
  const [editVariantOriginalPrice, setEditVariantOriginalPrice] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newImgUrl, setNewImgUrl] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [savingNew, setSavingNew] = useState(false);
  const [catalogShowAll, setCatalogShowAll] = useState(false);
  const [showAddStockModal, setShowAddStockModal] = useState(false);
  const [stockProductId, setStockProductId] = useState("");
  const [stockQuantity, setStockQuantity] = useState("1");
  const [addingStock, setAddingStock] = useState(false);
  const [stockSuccessMessage, setStockSuccessMessage] = useState("");
  const [productPendingDeleteId, setProductPendingDeleteId] = useState<number | null>(null);
  const [deletingProduct, setDeletingProduct] = useState(false);
  const [variantPriceConfirmation, setVariantPriceConfirmation] = useState<{
    variant: AdminVariant;
    payload: VariantEditPayload;
  } | null>(null);
  const [savingVariant, setSavingVariant] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const catalog: AdminCatalog = await getAdminCatalog({ limit: catalogShowAll ? 1000 : 200 });
      const normalizedVariants = normalizeVariantsByProduct(catalog.variants_by_product);
      setProducts(catalog.products);
      setCategories(catalog.categories);
      setVariantsByProduct(normalizedVariants);
      if (!newCategory && catalog.categories[0]?.name) {
        setNewCategory(catalog.categories[0].name);
      }
    } catch {
      setError("No se pudo cargar el catalogo admin.");
    } finally {
      setLoading(false);
    }
  }, [newCategory, catalogShowAll]);

  useEffect(() => {
    if (CATALOG_DEPENDENT_SECTIONS.includes(adminSection)) {
      void loadAll();
    }
  }, [adminSection, loadAll]);

  const categoriesState = useAdminCategories({
    categories,
    products,
    reload: loadAll,
    setError,
    newCategory,
    setNewCategory
  });

  async function onCreateProduct(event: FormEvent) {
    event.preventDefault();
    if (!categoriesState.hasCategories) {
      setError("Primero crea al menos una categoria en admin.");
      return;
    }
    setSavingNew(true);
    setError("");
    try {
      await createAdminProduct({
        name: newName.trim(),
        description: newDescription.trim() || null,
        img_url: newImgUrl.trim() || null,
        category: newCategory,
        active: true
      });
      setNewName("");
      setNewDescription("");
      setNewImgUrl("");
      await loadAll();
    } catch {
      setError("No se pudo crear el producto.");
    } finally {
      setSavingNew(false);
    }
  }

  function onOpenAddStockModal() {
    if (!stockProductId && products[0]?.id) {
      setStockProductId(String(products[0].id));
    }
    setStockQuantity("1");
    setStockSuccessMessage("");
    setShowAddStockModal(true);
    setError("");
  }

  async function onConfirmAddStock(selectedVariantIds: number[]) {
    const parsedProductId = Number.parseInt(stockProductId, 10);
    const parsedQty = Number.parseInt(stockQuantity, 10);
    if (Number.isNaN(parsedProductId) || parsedProductId <= 0) {
      setError("Selecciona un producto valido.");
      return;
    }
    if (Number.isNaN(parsedQty) || parsedQty <= 0) {
      setError("Cantidad de stock invalida.");
      return;
    }

    const variants = variantsByProduct[parsedProductId] ?? [];
    if (variants.length === 0) {
      setError("El producto seleccionado no tiene variantes para actualizar stock.");
      return;
    }
    if (!selectedVariantIds.length) {
      setError("Selecciona al menos una variante.");
      return;
    }
    const variantIdSet = new Set(selectedVariantIds.map((id) => Number(id)));
    const variantsToUpdate = variants.filter((variant) => variantIdSet.has(Number(variant.id)));
    if (variantsToUpdate.length === 0) {
      setError("Las variantes seleccionadas no son validas para el producto.");
      return;
    }

    setAddingStock(true);
    setError("");
    setStockSuccessMessage("");
    try {
      const updatedVariants = await Promise.all(
        variantsToUpdate.map((variant) =>
          patchAdminVariant(variant.id, {
            stock: Number(variant.stock ?? 0) + parsedQty
          })
        )
      );
      setVariantsByProduct((prev) => {
        const current = prev[parsedProductId] ?? [];
        const updates = new Map(updatedVariants.map((variant) => [variant.id, variant]));
        return {
          ...prev,
          [parsedProductId]: current.map((variant) => updates.get(variant.id) ?? variant)
        };
      });
      setProducts((prev) =>
        prev.map((product) => {
          if (product.id !== parsedProductId) return product;
          const current = variantsByProduct[parsedProductId] ?? [];
          const updates = new Map(updatedVariants.map((variant) => [variant.id, variant]));
          const nextVariants = current.map((variant) => updates.get(variant.id) ?? variant);
          return deriveProductFromVariants(product, nextVariants);
        })
      );
      setStockProductId("");
      setStockQuantity("0");
      setStockSuccessMessage(`Stock actualizado en ${variantsToUpdate.length} variante(s).`);
    } catch {
      setError("No se pudo agregar stock al producto.");
    } finally {
      setAddingStock(false);
    }
  }

  const onRequestDeleteProduct = useCallback((productId: number) => {
    setOpenProductMenuId(null);
    setProductPendingDeleteId(productId);
  }, []);

  function onCancelDeleteProduct() {
    setProductPendingDeleteId(null);
  }

  async function onConfirmDeleteProduct() {
    if (productPendingDeleteId === null) return;
    setError("");
    setDeletingProduct(true);
    try {
      await deleteAdminProduct(productPendingDeleteId);
      await loadAll();
    } catch {
      setError("No se pudo eliminar el producto.");
    } finally {
      setDeletingProduct(false);
      setProductPendingDeleteId(null);
    }
  }

  const onStartEdit = useCallback(
    (product: AdminProduct) => {
      setExpandedProducts((prev) => ({ ...prev, [product.id]: true }));
      setOpenProductMenuId(null);
      setEditingProductId(product.id);
      setEditName(product.name || "");
      setEditDescription(product.description || "");
      setEditImgUrl(product.img_url || "");
      setEditCategory(product.category || categories[0]?.name || "");
      setEditActive(Boolean(product.active));
    },
    [categories]
  );

  async function onSaveProductEdit() {
    if (!editingProductId) return;
    setError("");
    try {
      const currentProduct = products.find((product) => product.id === editingProductId) ?? null;
      const updatedProduct = await patchAdminProduct(editingProductId, {
        name: editName.trim(),
        description: editDescription.trim() || null,
        img_url: editImgUrl.trim() || null,
        category: editCategory,
        active: editActive
      });
      setEditingProductId(null);
      setOpenProductMenuId(null);
      setProducts((prev) => prev.map((product) => (product.id === editingProductId ? updatedProduct : product)));
      if (currentProduct && currentProduct.active !== updatedProduct.active) {
        setVariantsByProduct((prev) => {
          const current = prev[updatedProduct.id] ?? [];
          if (current.length === 0) return prev;
          return {
            ...prev,
            [updatedProduct.id]: current.map((variant) => ({ ...variant, active: updatedProduct.active }))
          };
        });
      }
    } catch {
      setError("No se pudo actualizar el producto.");
    }
  }

  const onStartVariantEdit = useCallback((variant: AdminVariant) => {
    setEditingVariantId(variant.id);
    setEditVariantSku(variant.sku || "");
    setEditVariantSize(variant.size || "");
    setEditVariantColor(variant.color || "");
    setEditVariantImgUrl(variant.img_url || "");
    setEditVariantStock(String(variant.stock ?? 0));
    setEditVariantActive(Boolean(variant.active));
    setEnableVariantPriceEdit(false);
    setEditVariantPrice(String(variant.price ?? 0));
    setEditVariantOriginalPrice(variant.price ?? 0);
  }, []);

  const toggleProductExpanded = useCallback((productId: number) => {
    setExpandedProducts((prev) => ({ ...prev, [productId]: !prev[productId] }));
  }, []);

  async function applyVariantEdit(variant: AdminVariant, payload: VariantEditPayload) {
    try {
      const updatedVariant = await patchAdminVariant(variant.id, payload);
      setEditingVariantId(null);
      setVariantsByProduct((prev) => {
        const current = prev[updatedVariant.product_id] ?? [];
        return {
          ...prev,
          [updatedVariant.product_id]: current.map((row) => (row.id === updatedVariant.id ? updatedVariant : row))
        };
      });
      setProducts((prev) =>
        prev.map((product) => {
          if (product.id !== updatedVariant.product_id) return product;
          const current = variantsByProduct[updatedVariant.product_id] ?? [];
          const nextVariants = current.map((row) => (row.id === updatedVariant.id ? updatedVariant : row));
          return deriveProductFromVariants(product, nextVariants);
        })
      );
    } catch {
      setError("No se pudo actualizar la variante.");
    }
  }

  async function onSaveVariantEdit(variant: AdminVariant) {
    if (editingVariantId !== variant.id) return;
    setError("");

    const stockAsInt = Number.parseInt(editVariantStock, 10);
    if (Number.isNaN(stockAsInt) || stockAsInt < 0) {
      setError("Stock invalido.");
      return;
    }

    const payload: VariantEditPayload = {
      sku: editVariantSku.trim(),
      size: editVariantSize.trim() || null,
      color: editVariantColor.trim() || null,
      img_url: editVariantImgUrl.trim() || null,
      stock: stockAsInt,
      active: editVariantActive
    };

    if (enableVariantPriceEdit) {
      const priceAsInt = Number.parseInt(editVariantPrice, 10);
      if (Number.isNaN(priceAsInt) || priceAsInt < 0) {
        setError("Precio invalido.");
        return;
      }
      payload.price = priceAsInt;
      if (priceAsInt !== editVariantOriginalPrice) {
        setVariantPriceConfirmation({ variant, payload });
        return;
      }
    }

    await applyVariantEdit(variant, payload);
  }

  function onCancelVariantPriceChange() {
    setVariantPriceConfirmation(null);
  }

  async function onConfirmVariantPriceChange() {
    if (!variantPriceConfirmation) return;
    const { variant, payload } = variantPriceConfirmation;
    setSavingVariant(true);
    try {
      await applyVariantEdit(variant, payload);
    } finally {
      setSavingVariant(false);
      setVariantPriceConfirmation(null);
    }
  }

  const productsSorted = useMemo(
    () => [...products].sort((a, b) => String(a.name).localeCompare(String(b.name))),
    [products]
  );

  const productsByCategory = useMemo(() => {
    const grouped: Record<string, AdminProduct[]> = {};
    for (const product of productsSorted) {
      const categoryName = String(product.category || "Sin categoria");
      if (!grouped[categoryName]) {
        grouped[categoryName] = [];
      }
      grouped[categoryName].push(product);
    }
    return grouped;
  }, [productsSorted]);

  const visibleProducts = useMemo(() => {
    if (categoriesState.catalogCategoryFilter === "all") {
      return productsSorted;
    }
    return productsSorted.filter(
      (product) => String(product.category || "") === categoriesState.catalogCategoryFilter
    );
  }, [productsSorted, categoriesState.catalogCategoryFilter]);

  return {
    categories,
    ...categoriesState,
    productsSorted,
    productsByCategory,
    visibleProducts,
    variantsByProduct,
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
    showCreateProductForm,
    setShowCreateProductForm,
    onCreateProduct,
    savingNew,
    newName,
    setNewName,
    newCategory,
    setNewCategory,
    newDescription,
    setNewDescription,
    newImgUrl,
    setNewImgUrl,
    loading,
    error,
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
    onConfirmVariantPriceChange
  };
}
