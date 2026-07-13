import { useEffect, useMemo, useState } from "react";
import { createAdminDiscount, deleteAdminDiscount, listAdminDiscounts, patchAdminDiscount, type AdminDiscount } from "../../../services/admin-discounts-api";
import type { AdminCategory, AdminProduct, AdminVariant } from "../../../services/admin-catalog-api";
import type { AdminSection } from "../types";

export function useAdminDiscounts(params: {
  adminSection: AdminSection;
  categories: AdminCategory[];
  productsSorted: AdminProduct[];
  variantsByProduct: Record<number, AdminVariant[]>;
}) {
  const { adminSection, categories, productsSorted, variantsByProduct } = params;
  const [discounts, setDiscounts] = useState<AdminDiscount[]>([]);
  const [discountsLoading, setDiscountsLoading] = useState(false);
  const [discountsError, setDiscountsError] = useState("");
  const [showCreateDiscountForm, setShowCreateDiscountForm] = useState(false);
  const [newDiscountName, setNewDiscountName] = useState("");
  const [newDiscountType, setNewDiscountType] = useState<"percent" | "fixed">("percent");
  const [newDiscountValue, setNewDiscountValue] = useState("10");
  const [newDiscountTarget, setNewDiscountTarget] = useState<"all" | "category" | "products">("all");
  const [newDiscountCategoryId, setNewDiscountCategoryId] = useState("");
  const [showDiscountProductPicker, setShowDiscountProductPicker] = useState(false);
  const [discountPickerExpandedProducts, setDiscountPickerExpandedProducts] = useState<Record<number, boolean>>({});
  const [selectedDiscountProductIds, setSelectedDiscountProductIds] = useState<Record<number, boolean>>({});
  const [selectedDiscountVariantIds, setSelectedDiscountVariantIds] = useState<Record<number, boolean>>({});
  const [newDiscountActive, setNewDiscountActive] = useState(true);
  const [discountPendingDeleteId, setDiscountPendingDeleteId] = useState<number | null>(null);
  const [deletingDiscount, setDeletingDiscount] = useState(false);
  const [togglingDiscountId, setTogglingDiscountId] = useState<number | null>(null);

  async function loadDiscounts() {
    setDiscountsLoading(true);
    setDiscountsError("");
    try {
      const rows = await listAdminDiscounts();
      setDiscounts(rows);
    } catch {
      setDiscountsError("No se pudieron cargar los descuentos.");
    } finally {
      setDiscountsLoading(false);
    }
  }

  useEffect(() => {
    if (adminSection === "descuentos") {
      void loadDiscounts();
    }
  }, [adminSection]);

  function toggleDiscountPickerProductExpanded(productId: number) {
    setDiscountPickerExpandedProducts((prev) => ({ ...prev, [productId]: !prev[productId] }));
  }

  function toggleDiscountProductSelection(productId: number, checked: boolean) {
    const variants = variantsByProduct[productId] ?? [];
    setSelectedDiscountProductIds((prev) => ({ ...prev, [productId]: checked }));
    setSelectedDiscountVariantIds((prev) => {
      const next = { ...prev };
      for (const variant of variants) {
        next[variant.id] = checked;
      }
      return next;
    });
  }

  function toggleDiscountVariantSelection(productId: number, variantId: number, checked: boolean) {
    const variants = variantsByProduct[productId] ?? [];
    setSelectedDiscountVariantIds((prev) => {
      const next = { ...prev, [variantId]: checked };
      setSelectedDiscountProductIds((prevProducts) => ({
        ...prevProducts,
        [productId]: variants.length > 0 && variants.every((variant) => !!next[variant.id])
      }));
      return next;
    });
  }

  async function onCreateDiscount() {
    setDiscountsError("");
    try {
      const parsedValue = Number.parseInt(newDiscountValue, 10);
      if (Number.isNaN(parsedValue) || parsedValue <= 0) {
        setDiscountsError("Valor de descuento invalido.");
        return;
      }
      const variantToProductId = new Map<number, number>();
      for (const productVariants of Object.values(variantsByProduct)) {
        for (const variant of productVariants) {
          variantToProductId.set(variant.id, variant.product_id);
        }
      }
      const selectedProductIdsFromVariants = Array.from(
        new Set(
          Object.entries(selectedDiscountVariantIds)
            .filter(([, selected]) => selected)
            .map(([variantId]) => variantToProductId.get(Number.parseInt(variantId, 10)))
            .filter((productId): productId is number => typeof productId === "number" && productId > 0)
        )
      );
      const selectedDirectProductIds = Object.entries(selectedDiscountProductIds)
        .filter(([, selected]) => selected)
        .map(([productId]) => Number.parseInt(productId, 10))
        .filter((productId) => Number.isFinite(productId) && productId > 0);
      const mergedProductIds = Array.from(new Set([...selectedProductIdsFromVariants, ...selectedDirectProductIds]));

      if (newDiscountTarget === "category") {
        const parsedCategoryId = Number.parseInt(newDiscountCategoryId, 10);
        if (Number.isNaN(parsedCategoryId) || parsedCategoryId <= 0) {
          setDiscountsError("Elegi una categoria valida.");
          return;
        }
      }
      if (newDiscountTarget === "products" && mergedProductIds.length === 0) {
        setDiscountsError("Selecciona al menos un producto o variante.");
        return;
      }

      const scope: "all" | "category" | "product" | "product_list" =
        newDiscountTarget === "all"
          ? "all"
          : newDiscountTarget === "category"
            ? "category"
            : mergedProductIds.length === 1
              ? "product"
              : "product_list";

      await createAdminDiscount({
        name: newDiscountName.trim(),
        type: newDiscountType,
        value: parsedValue,
        scope,
        category_id: scope === "category" ? Number.parseInt(newDiscountCategoryId, 10) : null,
        product_id: scope === "product" ? mergedProductIds[0] : null,
        product_ids: scope === "product_list" ? mergedProductIds : [],
        is_active: newDiscountActive
      });
      setNewDiscountName("");
      setNewDiscountValue("10");
      setNewDiscountTarget("all");
      setNewDiscountCategoryId("");
      setSelectedDiscountProductIds({});
      setSelectedDiscountVariantIds({});
      setShowDiscountProductPicker(false);
      setNewDiscountActive(true);
      setShowCreateDiscountForm(false);
      await loadDiscounts();
    } catch {
      setDiscountsError("No se pudo crear el descuento.");
    }
  }

  async function onToggleDiscountActive(discount: AdminDiscount) {
    setDiscountsError("");
    setTogglingDiscountId(discount.id);
    try {
      await patchAdminDiscount(discount.id, { is_active: !discount.is_active });
      await loadDiscounts();
    } catch {
      setDiscountsError("No se pudo actualizar el descuento.");
    } finally {
      setTogglingDiscountId(null);
    }
  }

  function onRequestDeleteDiscount(discountId: number) {
    setDiscountPendingDeleteId(discountId);
  }

  function onCancelDeleteDiscount() {
    setDiscountPendingDeleteId(null);
  }

  async function onConfirmDeleteDiscount() {
    if (discountPendingDeleteId === null) return;
    setDiscountsError("");
    setDeletingDiscount(true);
    try {
      await deleteAdminDiscount(discountPendingDeleteId);
      await loadDiscounts();
    } catch {
      setDiscountsError("No se pudo eliminar el descuento.");
    } finally {
      setDeletingDiscount(false);
      setDiscountPendingDeleteId(null);
    }
  }

  const selectedDiscountVariantCount = useMemo(
    () => Object.values(selectedDiscountVariantIds).filter(Boolean).length,
    [selectedDiscountVariantIds]
  );
  const selectedDiscountProductCount = useMemo(() => {
    const direct = Object.entries(selectedDiscountProductIds)
      .filter(([, selected]) => selected)
      .map(([productId]) => Number.parseInt(productId, 10))
      .filter((productId) => Number.isFinite(productId) && productId > 0);
    const variantProducts = Object.entries(selectedDiscountVariantIds)
      .filter(([, selected]) => selected)
      .map(([variantId]) => {
        const numericVariantId = Number.parseInt(variantId, 10);
        for (const productVariants of Object.values(variantsByProduct)) {
          const match = productVariants.find((variant) => variant.id === numericVariantId);
          if (match) return match.product_id;
        }
        return null;
      })
      .filter((productId): productId is number => typeof productId === "number" && productId > 0);
    return new Set([...direct, ...variantProducts]).size;
  }, [selectedDiscountProductIds, selectedDiscountVariantIds, variantsByProduct]);

  return {
    categories,
    productsSorted,
    variantsByProduct,
    discounts,
    discountsLoading,
    discountsError,
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
    newDiscountActive,
    setNewDiscountActive,
    showDiscountProductPicker,
    setShowDiscountProductPicker,
    selectedDiscountProductCount,
    selectedDiscountVariantCount,
    discountPickerExpandedProducts,
    selectedDiscountProductIds,
    selectedDiscountVariantIds,
    toggleDiscountPickerProductExpanded,
    toggleDiscountProductSelection,
    toggleDiscountVariantSelection,
    onCreateDiscount,
    onToggleDiscountActive,
    togglingDiscountId,
    discountPendingDeleteId,
    deletingDiscount,
    onRequestDeleteDiscount,
    onCancelDeleteDiscount,
    onConfirmDeleteDiscount
  };
}
