import { useEffect, useMemo, useState, type FormEvent } from "react";
import { createAdminSale, searchAdminUsers, type AdminSearchUser } from "../../../services/admin-sales-api";
import type { AdminProduct, AdminVariant } from "../../../services/admin-catalog-api";
import { toUserMessage } from "../../../services/http-errors";
import type { AdminSection } from "../types";

type SaleDraftItem = {
  variant_id: number;
  quantity: number;
  label: string;
  unit_price: number;
  line_total: number;
  sold_by?: "unit" | "measure";
  measure_unit?: string | null;
  step?: number;
};

export function useAdminSales(params: {
  adminSection: AdminSection;
  productsSorted: AdminProduct[];
  variantsByProduct: Record<number, AdminVariant[]>;
}) {
  const { productsSorted, variantsByProduct } = params;
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [dni, setDni] = useState("");
  const [selectedUser, setSelectedUser] = useState<AdminSearchUser | null>(null);

  const [showUserSearch, setShowUserSearch] = useState(false);
  const [searchFirstName, setSearchFirstName] = useState("");
  const [searchLastName, setSearchLastName] = useState("");
  const [searchEmail, setSearchEmail] = useState("");
  const [searchDni, setSearchDni] = useState("");
  const [searchPhone, setSearchPhone] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchResults, setSearchResults] = useState<AdminSearchUser[]>([]);
  const [pendingSelectedUser, setPendingSelectedUser] = useState<AdminSearchUser | null>(null);

  const [showProductSearch, setShowProductSearch] = useState(false);
  const [productSearchQuery, setProductSearchQuery] = useState("");
  const [pendingSelectedProductId, setPendingSelectedProductId] = useState<number | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null);

  const [newVariantId, setNewVariantId] = useState("");
  const [newQuantity, setNewQuantity] = useState("1");
  const [items, setItems] = useState<SaleDraftItem[]>([]);

  const [registerPayment, setRegisterPayment] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<"cash" | "bank_transfer">("cash");
  const [amountPaid, setAmountPaid] = useState("");
  const [changeAmount, setChangeAmount] = useState("0");
  const [paymentRef, setPaymentRef] = useState("");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const total = useMemo(
    () => items.reduce((sum, row) => sum + row.line_total, 0),
    [items]
  );
  const selectedProduct = useMemo(
    () => productsSorted.find((row) => row.id === selectedProductId) ?? null,
    [productsSorted, selectedProductId]
  );
  const productSearchResults = useMemo(() => {
    const query = productSearchQuery.trim().toLocaleLowerCase();
    if (!query) return productsSorted.slice(0, 50);
    return productsSorted.filter((product) => {
      const productName = String(product.name || "").toLocaleLowerCase();
      const categoryName = String(product.category || "").toLocaleLowerCase();
      return productName.includes(query) || categoryName.includes(query);
    }).slice(0, 50);
  }, [productsSorted, productSearchQuery]);
  const selectedProductVariants = useMemo(() => {
    if (!selectedProduct) return [];
    return (variantsByProduct[selectedProduct.id] || []).filter((variant) => Boolean(variant.active));
  }, [selectedProduct, variantsByProduct]);

  function onSelectFoundUser(user: AdminSearchUser) {
    setSelectedUser(user);
    setFirstName(user.first_name || "");
    setLastName(user.last_name || "");
    setEmail(user.email || "");
    setPhone(user.phone || "");
    setDni(user.dni || "");
    setShowUserSearch(false);
    setSearchResults([]);
    setSearchError("");
  }

  function openUserSearchModal() {
    setShowUserSearch(true);
  }

  function closeUserSearchModal() {
    setShowUserSearch(false);
    setSearchError("");
    setSearchResults([]);
    setPendingSelectedUser(null);
  }

  function onClearSelectedUser() {
    setSelectedUser(null);
  }

  function openProductSearchModal() {
    setShowProductSearch(true);
  }

  function closeProductSearchModal() {
    setShowProductSearch(false);
    setPendingSelectedProductId(null);
  }

  function onTogglePendingProduct(productId: number, checked: boolean) {
    setPendingSelectedProductId(checked ? productId : null);
  }

  function onConfirmPendingProduct() {
    if (!pendingSelectedProductId) return;
    setSelectedProductId(pendingSelectedProductId);
    setNewVariantId("");
    setShowProductSearch(false);
    setPendingSelectedProductId(null);
  }

  function onClearSelectedProduct() {
    setSelectedProductId(null);
    setNewVariantId("");
  }

  async function onSearchUsers() {
    const hasFilters = [searchFirstName, searchLastName, searchEmail, searchDni, searchPhone]
      .some((value) => value.trim().length > 0);
    if (!hasFilters) {
      setSearchError("");
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    setSearchError("");
    try {
      const users = await searchAdminUsers({
        first_name: searchFirstName.trim() || undefined,
        last_name: searchLastName.trim() || undefined,
        email: searchEmail.trim() || undefined,
        dni: searchDni.trim() || undefined,
        phone: searchPhone.trim() || undefined,
        limit: 20
      });
      setSearchResults(users);
    } catch (apiError: unknown) {
      setSearchError(toUserMessage(apiError, "generic"));
    } finally {
      setSearchLoading(false);
    }
  }

  useEffect(() => {
    if (!showUserSearch) return;
    const timer = window.setTimeout(() => {
      void onSearchUsers();
    }, 250);
    return () => {
      window.clearTimeout(timer);
    };
  }, [showUserSearch, searchFirstName, searchLastName, searchEmail, searchDni, searchPhone]);

  function onTogglePendingUser(user: AdminSearchUser, checked: boolean) {
    setPendingSelectedUser(checked ? user : null);
  }

  function onConfirmPendingUser() {
    if (!pendingSelectedUser) return;
    onSelectFoundUser(pendingSelectedUser);
  }

  function onAddItem() {
    if (!selectedProduct) {
      setError("Primero selecciona un producto.");
      return;
    }
    const parsedVariantId = Number.parseInt(newVariantId, 10);
    const parsedQty = Number.parseInt(newQuantity, 10);
    if (Number.isNaN(parsedVariantId) || parsedVariantId <= 0 || Number.isNaN(parsedQty) || parsedQty <= 0) {
      setError("Selecciona una variante y cantidad valida.");
      return;
    }
    const variant = selectedProductVariants.find((row) => row.id === parsedVariantId);
    if (!variant) {
      setError("Variante invalida.");
      return;
    }
    const unitPrice = Number(variant.price ?? 0);
    const lineLabel = `${selectedProduct.name} | ${variant.sku} (${variant.size || "-"} / ${variant.color || "-"})`;
    setItems((prev) => {
      const existing = prev.find((row) => row.variant_id === parsedVariantId);
      if (existing) {
        return prev.map((row) =>
          row.variant_id === parsedVariantId
            ? {
                ...row,
                quantity: row.quantity + parsedQty,
                line_total: unitPrice * (row.quantity + parsedQty)
              }
            : row
        );
      }
      return [
        ...prev,
        {
          variant_id: parsedVariantId,
          quantity: parsedQty,
          label: lineLabel,
          unit_price: unitPrice,
          line_total: unitPrice * parsedQty,
          sold_by: variant.sold_by ?? "unit",
          measure_unit: variant.measure_unit ?? null,
          step: variant.step ?? 1
        }
      ];
    });
    setNewVariantId("");
    setNewQuantity("1");
    setError("");
  }

  function removeItem(variantId: number) {
    setItems((prev) => prev.filter((row) => row.variant_id !== variantId));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    if (items.length === 0) {
      setError("Agrega al menos un producto.");
      return;
    }
    if (!selectedUser && (!firstName.trim() || !lastName.trim() || !email.trim() || !phone.trim())) {
      setError("Completa nombre, apellido, email y telefono o selecciona un usuario existente.");
      return;
    }
    if (registerPayment && !amountPaid.trim()) {
      setError("Ingresa el monto pagado.");
      return;
    }

    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const payload = {
        customer: selectedUser
          ? { mode: "existing" as const, user_id: selectedUser.id }
          : {
              mode: "new" as const,
              first_name: firstName.trim(),
              last_name: lastName.trim(),
              email: email.trim(),
              phone: phone.trim(),
              dni: dni.trim() || null
            },
        items: items.map((item) => ({
          variant_id: item.variant_id,
          quantity: item.quantity
        })),
        register_payment: registerPayment,
        payment: registerPayment
          ? {
              method: paymentMethod,
              amount_paid: Number.parseInt(amountPaid, 10),
              change_amount: paymentMethod === "cash" ? Number.parseInt(changeAmount || "0", 10) : undefined,
              payment_ref: paymentRef.trim() || undefined
            }
          : undefined
      };
      const result = await createAdminSale(payload);
      setSuccess(
        registerPayment
          ? `Venta registrada. Orden #${result.order.id} en estado ${result.order.status}.`
          : `Orden registrada. Orden #${result.order.id} en estado ${result.order.status}.`
      );
      setItems([]);
      setNewVariantId("");
      setNewQuantity("1");
      setRegisterPayment(false);
      setAmountPaid("");
      setChangeAmount("0");
      setPaymentRef("");
    } catch (apiError: unknown) {
      setError(toUserMessage(apiError, "generic"));
    } finally {
      setSaving(false);
    }
  }

  return {
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
    onSubmit
  };
}
