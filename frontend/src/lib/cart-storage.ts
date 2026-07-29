export type CartItem = {
  product_id: number;
  product_name: string;
  variant_id: number;
  option_label: string;
  unit_price: number;
  quantity: number;
  img_url: string | null;
  // Productos por cantidad/peso (docs/products_by_measure.md). Opcionales para no
  // romper carritos ya guardados en localStorage: ausente = producto por unidad.
  sold_by?: "unit" | "measure";
  measure_unit?: string | null;
  step?: number;
};

const CART_KEY = "pb_cart_items";
const CART_EVENT_NAME = "pb-cart-updated";

function emitCartUpdated(): void {
  window.dispatchEvent(new CustomEvent(CART_EVENT_NAME));
}

export function readCart(): CartItem[] {
  try {
    const raw = localStorage.getItem(CART_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as CartItem[];
  } catch {
    return [];
  }
}

export function writeCart(items: CartItem[]): void {
  localStorage.setItem(CART_KEY, JSON.stringify(items));
  emitCartUpdated();
}

export function addToCart(item: CartItem): void {
  const current = readCart();
  const existing = current.find(
    (row) => row.product_id === item.product_id && row.variant_id === item.variant_id
  );
  if (existing) {
    existing.quantity += item.quantity;
  } else {
    current.push(item);
  }
  writeCart(current);
}

export function updateCartItemQuantity(variantId: number, nextQuantity: number): CartItem[] {
  const normalizedQuantity = Math.max(1, Math.trunc(nextQuantity));
  const nextItems = readCart().map((item) =>
    item.variant_id === variantId ? { ...item, quantity: normalizedQuantity } : item
  );
  writeCart(nextItems);
  return nextItems;
}

export function removeCartItem(variantId: number): CartItem[] {
  const nextItems = readCart().filter((item) => item.variant_id !== variantId);
  writeCart(nextItems);
  return nextItems;
}

export function hasMeasureItems(items: CartItem[]): boolean {
  return items.some((item) => item.sold_by === "measure");
}

export function incrementCartItem(variantId: number, max = 10): CartItem[] {
  const nextItems = readCart().map((item) => {
    if (item.variant_id !== variantId) return item;
    // Los productos por cantidad se mueven de a un paso y no tienen el tope de 10
    // (el tope es anti-abuso del pago self-service, que estos no usan).
    const cap = item.sold_by === "measure" ? Number.MAX_SAFE_INTEGER : Math.max(1, Math.trunc(max));
    return { ...item, quantity: Math.min(cap, item.quantity + 1) };
  });
  writeCart(nextItems);
  return nextItems;
}

export function decrementCartItem(variantId: number): CartItem[] {
  const nextItems = readCart().map((item) => {
    if (item.variant_id !== variantId) return item;
    return { ...item, quantity: Math.max(1, item.quantity - 1) };
  });
  writeCart(nextItems);
  return nextItems;
}

export function cartCount(): number {
  return readCart().reduce((acc, item) => acc + Number(item.quantity || 0), 0);
}

export function clearCart(): void {
  localStorage.removeItem(CART_KEY);
  emitCartUpdated();
}

export function subscribeToCartUpdates(listener: () => void): () => void {
  window.addEventListener(CART_EVENT_NAME, listener);
  return () => window.removeEventListener(CART_EVENT_NAME, listener);
}
