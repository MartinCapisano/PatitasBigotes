import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  addToCart,
  cartCount,
  clearCart,
  decrementCartItem,
  incrementCartItem,
  readCart,
  removeCartItem,
  subscribeToCartUpdates,
  updateCartItemQuantity,
  type CartItem
} from "./cart-storage";

function buildItem(overrides: Partial<CartItem> = {}): CartItem {
  return {
    product_id: 1,
    product_name: "Collar",
    variant_id: 10,
    option_label: "M/Azul",
    unit_price: 5000,
    quantity: 1,
    img_url: null,
    ...overrides
  };
}

describe("cart-storage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns an empty cart when nothing is stored", () => {
    expect(readCart()).toEqual([]);
    expect(cartCount()).toBe(0);
  });

  it("returns an empty cart when localStorage has corrupted JSON", () => {
    localStorage.setItem("pb_cart_items", "{not-json");
    expect(readCart()).toEqual([]);
  });

  it("adds a new item to an empty cart", () => {
    addToCart(buildItem({ quantity: 2 }));

    const cart = readCart();
    expect(cart).toHaveLength(1);
    expect(cart[0].quantity).toBe(2);
  });

  it("merges quantities when adding the same product+variant twice", () => {
    addToCart(buildItem({ quantity: 2 }));
    addToCart(buildItem({ quantity: 3 }));

    const cart = readCart();
    expect(cart).toHaveLength(1);
    expect(cart[0].quantity).toBe(5);
  });

  it("keeps distinct entries for the same product with a different variant", () => {
    addToCart(buildItem({ variant_id: 10, quantity: 1 }));
    addToCart(buildItem({ variant_id: 11, quantity: 1 }));

    expect(readCart()).toHaveLength(2);
  });

  it("updateCartItemQuantity clamps to a minimum of 1", () => {
    addToCart(buildItem({ quantity: 3 }));

    const result = updateCartItemQuantity(10, -5);

    expect(result[0].quantity).toBe(1);
  });

  it("updateCartItemQuantity truncates fractional quantities", () => {
    addToCart(buildItem({ quantity: 1 }));

    const result = updateCartItemQuantity(10, 4.9);

    expect(result[0].quantity).toBe(4);
  });

  it("incrementCartItem caps at the given max", () => {
    addToCart(buildItem({ quantity: 9 }));

    const result = incrementCartItem(10, 10);

    expect(result[0].quantity).toBe(10);
    expect(incrementCartItem(10, 10)[0].quantity).toBe(10);
  });

  it("decrementCartItem never goes below 1", () => {
    addToCart(buildItem({ quantity: 1 }));

    const result = decrementCartItem(10);

    expect(result[0].quantity).toBe(1);
  });

  it("removeCartItem drops only the matching variant", () => {
    addToCart(buildItem({ variant_id: 10 }));
    addToCart(buildItem({ variant_id: 11 }));

    const result = removeCartItem(10);

    expect(result).toHaveLength(1);
    expect(result[0].variant_id).toBe(11);
  });

  it("cartCount sums quantities across items", () => {
    addToCart(buildItem({ variant_id: 10, quantity: 2 }));
    addToCart(buildItem({ variant_id: 11, quantity: 3 }));

    expect(cartCount()).toBe(5);
  });

  it("clearCart empties the cart", () => {
    addToCart(buildItem());
    clearCart();

    expect(readCart()).toEqual([]);
  });

  it("notifies subscribers when the cart changes", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToCartUpdates(listener);

    addToCart(buildItem());
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    addToCart(buildItem({ variant_id: 99 }));
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
