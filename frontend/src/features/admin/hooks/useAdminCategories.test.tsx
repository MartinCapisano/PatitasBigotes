import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAdminCategories, type UseAdminCategoriesParams } from "./useAdminCategories";
import {
  type AdminCategory,
  type AdminProduct,
  createAdminCategory,
  deleteAdminCategory,
  patchAdminCategory,
} from "../../../services/admin-catalog-api";

vi.mock("../../../services/admin-catalog-api", () => ({
  createAdminCategory: vi.fn(),
  deleteAdminCategory: vi.fn(),
  patchAdminCategory: vi.fn(),
}));

function category(overrides: Partial<AdminCategory> = {}): AdminCategory {
  return { id: 1, name: "Accesorios", ...overrides } as AdminCategory;
}

function product(overrides: Partial<AdminProduct> = {}): AdminProduct {
  return { id: 1, name: "Collar", category: "Accesorios", ...overrides } as AdminProduct;
}

function makeParams(overrides: Partial<UseAdminCategoriesParams> = {}): UseAdminCategoriesParams {
  return {
    categories: [category()],
    products: [],
    reload: vi.fn().mockResolvedValue(undefined),
    setError: vi.fn(),
    newCategory: "",
    setNewCategory: vi.fn(),
    ...overrides,
  };
}

function submitEvent() {
  return { preventDefault: vi.fn() } as unknown as React.FormEvent;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useAdminCategories — create", () => {
  it("creates a category, reloads and resets the form on a valid name", async () => {
    const params = makeParams();
    vi.mocked(createAdminCategory).mockResolvedValue(category({ id: 2, name: "Alimento" }));

    const { result } = renderHook(() => useAdminCategories(params));
    act(() => {
      result.current.setNewCategoryName("  Alimento  ");
      result.current.setShowCreateCategoryForm(true);
    });

    await act(async () => {
      await result.current.onCreateCategory(submitEvent());
    });

    expect(createAdminCategory).toHaveBeenCalledWith({ name: "Alimento" });
    expect(params.reload).toHaveBeenCalledTimes(1);
    expect(params.setNewCategory).toHaveBeenCalledWith("Alimento");
    expect(result.current.showCreateCategoryForm).toBe(false);
    expect(result.current.catalogCategoryFilter).toBe("Alimento");
  });

  it("rejects an empty category name without calling the API", async () => {
    const params = makeParams();

    const { result } = renderHook(() => useAdminCategories(params));
    act(() => {
      result.current.setNewCategoryName("   ");
    });

    await act(async () => {
      await result.current.onCreateCategory(submitEvent());
    });

    expect(createAdminCategory).not.toHaveBeenCalled();
    expect(params.setError).toHaveBeenCalledWith("Nombre de categoria requerido.");
  });

  it("surfaces an error message when create fails", async () => {
    const params = makeParams();
    vi.mocked(createAdminCategory).mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() => useAdminCategories(params));
    act(() => {
      result.current.setNewCategoryName("Alimento");
    });

    await act(async () => {
      await result.current.onCreateCategory(submitEvent());
    });

    expect(params.setError).toHaveBeenCalledWith("No se pudo crear la categoria.");
    expect(result.current.creatingCategory).toBe(false);
  });
});

describe("useAdminCategories — edit", () => {
  it("saves an edited category name and reloads", async () => {
    const params = makeParams({ categories: [category({ id: 7, name: "Higiene" })] });
    vi.mocked(patchAdminCategory).mockResolvedValue(category({ id: 7, name: "Higiene Premium" }));

    const { result } = renderHook(() => useAdminCategories(params));
    act(() => {
      result.current.onStartCategoryEdit(category({ id: 7, name: "Higiene" }));
    });
    expect(result.current.editingCategoryId).toBe(7);

    act(() => {
      result.current.setEditCategoryName("Higiene Premium");
    });
    await act(async () => {
      await result.current.onSaveCategoryEdit();
    });

    expect(patchAdminCategory).toHaveBeenCalledWith(7, { name: "Higiene Premium" });
    expect(params.reload).toHaveBeenCalledTimes(1);
    expect(result.current.editingCategoryId).toBeNull();
  });

  it("does not call the API when saving an empty edited name", async () => {
    const params = makeParams({ categories: [category({ id: 7, name: "Higiene" })] });

    const { result } = renderHook(() => useAdminCategories(params));
    act(() => {
      result.current.onStartCategoryEdit(category({ id: 7, name: "Higiene" }));
      result.current.setEditCategoryName("  ");
    });

    await act(async () => {
      await result.current.onSaveCategoryEdit();
    });

    expect(patchAdminCategory).not.toHaveBeenCalled();
    expect(params.setError).toHaveBeenCalledWith("Nombre de categoria requerido.");
  });
});

describe("useAdminCategories — delete", () => {
  it("blocks opening the delete modal when every category is in use", () => {
    const params = makeParams({
      categories: [category({ id: 1, name: "Accesorios" })],
      products: [product({ category: "Accesorios" })],
    });

    const { result } = renderHook(() => useAdminCategories(params));
    act(() => {
      result.current.onOpenDeleteCategoryModal();
    });

    expect(result.current.showDeleteCategoryModal).toBe(false);
    expect(params.setError).toHaveBeenCalledWith(
      "No hay categorias eliminables (todas tienen productos)."
    );
  });

  it("exposes only unused categories as deletable", () => {
    const params = makeParams({
      categories: [
        category({ id: 1, name: "Accesorios" }),
        category({ id: 2, name: "Alimento" }),
      ],
      products: [product({ category: "Accesorios" })],
    });

    const { result } = renderHook(() => useAdminCategories(params));

    expect(result.current.deletableCategories.map((c) => c.name)).toEqual(["Alimento"]);
  });

  it("deletes the selected category and reloads", async () => {
    const params = makeParams({
      categories: [category({ id: 2, name: "Alimento" })],
      products: [],
    });
    vi.mocked(deleteAdminCategory).mockResolvedValue(category({ id: 2, name: "Alimento" }));

    const { result } = renderHook(() => useAdminCategories(params));
    act(() => {
      result.current.onOpenDeleteCategoryModal();
    });
    expect(result.current.showDeleteCategoryModal).toBe(true);
    expect(result.current.deleteCategoryId).toBe("2");

    await act(async () => {
      await result.current.onConfirmDeleteCategory();
    });

    expect(deleteAdminCategory).toHaveBeenCalledWith(2);
    expect(params.reload).toHaveBeenCalledTimes(1);
    expect(result.current.showDeleteCategoryModal).toBe(false);
    expect(result.current.catalogCategoryFilter).toBe("all");
  });

  it("rejects confirming a delete with an invalid selection", async () => {
    const params = makeParams();

    const { result } = renderHook(() => useAdminCategories(params));
    act(() => {
      result.current.setDeleteCategoryId("not-a-number");
    });

    await act(async () => {
      await result.current.onConfirmDeleteCategory();
    });

    expect(deleteAdminCategory).not.toHaveBeenCalled();
    expect(params.setError).toHaveBeenCalledWith("Selecciona una categoria valida.");
  });

  it("surfaces an error message when delete fails", async () => {
    const params = makeParams({ categories: [category({ id: 2, name: "Alimento" })] });
    vi.mocked(deleteAdminCategory).mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() => useAdminCategories(params));
    act(() => {
      result.current.onOpenDeleteCategoryModal();
    });
    await act(async () => {
      await result.current.onConfirmDeleteCategory();
    });

    await waitFor(() => {
      expect(params.setError).toHaveBeenCalledWith("No se pudo eliminar la categoria.");
    });
    expect(result.current.deletingCategory).toBe(false);
  });
});
