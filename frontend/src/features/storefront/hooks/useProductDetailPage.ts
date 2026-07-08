import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { addToCart } from "../../../lib/cart-storage";
import type { StorefrontProductDetail } from "../../../types";
import { fetchStorefrontProductById } from "../../../services/storefront-api";

const ADDED_TO_CART_MESSAGE_TIMEOUT_MS = 4000;

export function useProductDetailPage() {
  const params = useParams();
  const [product, setProduct] = useState<StorefrontProductDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedVariantId, setSelectedVariantId] = useState<number | null>(null);
  const [addedToCart, setAddedToCart] = useState(false);

  useEffect(() => {
    async function run() {
      setLoading(true);
      setError("");
      try {
        const id = Number(params.productId);
        const payload = await fetchStorefrontProductById(id);
        setProduct(payload.data);
        setSelectedVariantId(payload.data.options[0]?.variant_id ?? null);
      } catch {
        setError("No se pudo cargar el producto.");
      } finally {
        setLoading(false);
      }
    }
    void run();
  }, [params.productId]);

  const selectedOption =
    product?.options.find((option) => option.variant_id === selectedVariantId) ?? product?.options[0];
  const currentImageUrl =
    selectedOption?.effective_img_url ?? selectedOption?.img_url ?? product?.img_url ?? null;

  useEffect(() => {
    if (!addedToCart) return;
    const timeoutId = window.setTimeout(() => setAddedToCart(false), ADDED_TO_CART_MESSAGE_TIMEOUT_MS);
    return () => window.clearTimeout(timeoutId);
  }, [addedToCart]);

  function onBuy() {
    if (!product) return;
    if (!selectedOption || !selectedOption.in_stock) return;
    addToCart({
      product_id: product.id,
      product_name: product.name,
      variant_id: selectedOption.variant_id,
      option_label: selectedOption.label,
      unit_price: selectedOption.price,
      quantity: 1,
      img_url: selectedOption.effective_img_url ?? selectedOption.img_url ?? product.img_url
    });
    setAddedToCart(true);
  }

  return {
    product,
    loading,
    error,
    selectedVariantId,
    setSelectedVariantId,
    selectedOption,
    currentImageUrl,
    addedToCart,
    onBuy
  };
}
