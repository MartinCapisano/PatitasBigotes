import { useMemo, useState, type FormEvent } from "react";
import {
  type AdminCategory,
  type AdminProduct,
  createAdminCategory,
  deleteAdminCategory,
  patchAdminCategory
} from "../../../services/admin-catalog-api";

export type UseAdminCategoriesParams = {
  categories: AdminCategory[];
  products: AdminProduct[];
  reload: () => Promise<void>;
  setError: (message: string) => void;
  newCategory: string;
  setNewCategory: (name: string) => void;
};

export function useAdminCategories({
  categories,
  products,
  reload,
  setError,
  newCategory,
  setNewCategory
}: UseAdminCategoriesParams) {
  const [showCreateCategoryForm, setShowCreateCategoryForm] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState("");
  const [creatingCategory, setCreatingCategory] = useState(false);
  const [editingCategoryId, setEditingCategoryId] = useState<number | null>(null);
  const [editCategoryName, setEditCategoryName] = useState("");
  const [openCategoryMenuId, setOpenCategoryMenuId] = useState<number | null>(null);
  const [catalogCategoryFilter, setCatalogCategoryFilter] = useState<string>("all");
  const [showDeleteCategoryModal, setShowDeleteCategoryModal] = useState(false);
  const [deleteCategoryId, setDeleteCategoryId] = useState("");
  const [deletingCategory, setDeletingCategory] = useState(false);

  const hasCategories = categories.length > 0;

  const categoryNames = useMemo(
    () => categories.map((category) => category.name).sort((a, b) => a.localeCompare(b)),
    [categories]
  );

  const deletableCategories = useMemo(() => {
    const usedCategoryNames = new Set(products.map((product) => String(product.category || "")));
    return categories.filter((category) => !usedCategoryNames.has(category.name));
  }, [categories, products]);

  async function onCreateCategory(event: FormEvent) {
    event.preventDefault();
    const normalizedName = newCategoryName.trim();
    if (!normalizedName) {
      setError("Nombre de categoria requerido.");
      return;
    }
    setCreatingCategory(true);
    setError("");
    try {
      await createAdminCategory({ name: normalizedName });
      setNewCategoryName("");
      setShowCreateCategoryForm(false);
      await reload();
      setCatalogCategoryFilter(normalizedName);
      setNewCategory(normalizedName);
    } catch {
      setError("No se pudo crear la categoria.");
    } finally {
      setCreatingCategory(false);
    }
  }

  function onOpenDeleteCategoryModal() {
    if (!deletableCategories.length) {
      setError("No hay categorias eliminables (todas tienen productos).");
      return;
    }
    setDeleteCategoryId(String(deletableCategories[0].id));
    setShowDeleteCategoryModal(true);
    setError("");
  }

  async function onConfirmDeleteCategory() {
    const categoryId = Number.parseInt(deleteCategoryId, 10);
    if (Number.isNaN(categoryId) || categoryId <= 0) {
      setError("Selecciona una categoria valida.");
      return;
    }
    setDeletingCategory(true);
    setError("");
    try {
      await deleteAdminCategory(categoryId);
      setShowDeleteCategoryModal(false);
      setDeleteCategoryId("");
      setCatalogCategoryFilter("all");
      await reload();
    } catch {
      setError("No se pudo eliminar la categoria.");
    } finally {
      setDeletingCategory(false);
    }
  }

  function onStartCategoryEdit(category: AdminCategory) {
    setOpenCategoryMenuId(null);
    setEditingCategoryId(category.id);
    setEditCategoryName(category.name);
    setError("");
  }

  async function onSaveCategoryEdit() {
    if (!editingCategoryId) return;
    const normalizedName = editCategoryName.trim();
    if (!normalizedName) {
      setError("Nombre de categoria requerido.");
      return;
    }
    setError("");
    try {
      const previousCategory = categories.find((category) => category.id === editingCategoryId) ?? null;
      await patchAdminCategory(editingCategoryId, { name: normalizedName });
      setEditingCategoryId(null);
      setEditCategoryName("");
      await reload();
      if (previousCategory && catalogCategoryFilter === previousCategory.name) {
        setCatalogCategoryFilter(normalizedName);
      }
      if (newCategory === previousCategory?.name) {
        setNewCategory(normalizedName);
      }
    } catch {
      setError("No se pudo actualizar la categoria.");
    }
  }

  return {
    hasCategories,
    categoryNames,
    deletableCategories,
    showCreateCategoryForm,
    setShowCreateCategoryForm,
    newCategoryName,
    setNewCategoryName,
    creatingCategory,
    onCreateCategory,
    editingCategoryId,
    setEditingCategoryId,
    editCategoryName,
    setEditCategoryName,
    openCategoryMenuId,
    setOpenCategoryMenuId,
    onStartCategoryEdit,
    onSaveCategoryEdit,
    catalogCategoryFilter,
    setCatalogCategoryFilter,
    showDeleteCategoryModal,
    setShowDeleteCategoryModal,
    deleteCategoryId,
    setDeleteCategoryId,
    deletingCategory,
    onOpenDeleteCategoryModal,
    onConfirmDeleteCategory
  };
}
