import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import type { StorefrontProduct } from "../../../types";
import { fetchStorefrontCategories, fetchStorefrontProducts } from "../../../services/storefront-api";
import type { CategoryItem } from "../types";

export function useStorefrontPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [categories, setCategories] = useState<CategoryItem[]>([]);
  const [products, setProducts] = useState<StorefrontProduct[]>([]);
  const [sortBy, setSortBy] = useState<"price" | "name">("name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const selectedCategoryId = Number(searchParams.get("category_id") || 0) || null;
  const offset = Math.max(0, (page - 1) * pageSize);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const payload = await fetchStorefrontProducts({
        q: appliedQuery.trim() || undefined,
        category_id: selectedCategoryId ?? undefined,
        sort_by: sortBy,
        sort_order: sortDir,
        limit: pageSize,
        offset
      });
      setProducts(payload.data);
      const rawTotal = Number((payload.meta?.total as number | undefined) ?? 0);
      setTotal(Number.isFinite(rawTotal) ? rawTotal : 0);
    } catch {
      setError("No se pudo cargar el catalogo.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [selectedCategoryId, appliedQuery, sortBy, sortDir, page, pageSize]);

  useEffect(() => {
    async function run() {
      try {
        const payload = await fetchStorefrontCategories();
        setCategories(payload.data);
      } catch {
        setCategories([]);
      }
    }
    void run();
  }, []);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setAppliedQuery(query.trim());
    setPage(1);
  }

  function onCategoryClick(categoryId: number | null) {
    const next = new URLSearchParams(searchParams);
    if (categoryId === null) {
      next.delete("category_id");
    } else {
      next.set("category_id", String(categoryId));
    }
    setPage(1);
    setSearchParams(next);
  }

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / pageSize)), [total, pageSize]);

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const pageInfo = useMemo(() => {
    if (total === 0) {
      return { from: 0, to: 0 };
    }
    const from = offset + 1;
    const to = Math.min(offset + products.length, total);
    return { from, to };
  }, [offset, products.length, total]);

  return {
    query,
    setQuery,
    categories,
    sortBy,
    setSortBy,
    sortDir,
    setSortDir,
    page,
    setPage,
    pageSize,
    setPageSize,
    total,
    totalPages,
    pageInfo,
    loading,
    error,
    onSubmit,
    selectedCategoryId,
    onCategoryClick,
    products
  };
}
