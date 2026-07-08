import { Link } from "react-router-dom";
import { formatArs, useProductDetailPage } from "../features/storefront";

export function ProductDetailPage() {
  const detail = useProductDetailPage();

  if (detail.loading) return <p>Cargando...</p>;
  if (detail.error) return <p className="error">{detail.error}</p>;
  if (!detail.product) return <p>No encontrado.</p>;

  return (
    <section>
      <Link className="link-back" to="/home">
        Volver al catalogo
      </Link>

      <div className="product-detail-layout">
        <div>
          {detail.currentImageUrl ? (
            <img className="product-image product-image-detail" src={detail.currentImageUrl} alt={detail.product.name} />
          ) : (
            <div className="image-placeholder image-placeholder-detail">Sin imagen</div>
          )}
        </div>

        <div>
          <h1 className="page-title">{detail.product.name}</h1>
          <p className="page-subtitle">{detail.product.description ?? "Sin descripcion"}</p>
          {!detail.product.in_stock && <p className="warning">Este producto no tiene stock disponible.</p>}

          <h2 className="section-title">Opciones ({detail.product.option_axis})</h2>
          <div className="options-grid">
            {detail.product.options.map((option) => (
              <button
                key={option.variant_id}
                className={`chip ${option.in_stock ? "" : "chip-disabled"} ${
                  detail.selectedVariantId === option.variant_id ? "chip-selected" : ""
                }`}
                type="button"
                disabled={!option.in_stock}
                onClick={() => detail.setSelectedVariantId(option.variant_id)}
              >
                <span>{option.label}</span>
                {option.has_discount && option.price_original !== undefined ? (
                  <span className="detail-option-price">
                    <span className="price-original">{formatArs(option.price_original)}</span>
                    <strong className="price-final">{formatArs(option.price_final ?? option.price)}</strong>
                  </span>
                ) : (
                  <strong>{formatArs(option.price_final ?? option.price)}</strong>
                )}
              </button>
            ))}
          </div>

          <div className="detail-actions">
            <button className="btn" type="button" disabled={!detail.selectedOption?.in_stock} onClick={detail.onBuy}>
              Comprar
            </button>
          </div>
          {detail.addedToCart && (
            <p className="success">
              Producto agregado al carrito. <Link to="/checkout">Finalizar compra</Link>
            </p>
          )}
        </div>
      </div>

      <div className="product-payment-note">
        Metodos de pago: Transferencia bancaria, MercadoPago y Efectivo.
      </div>
    </section>
  );
}
