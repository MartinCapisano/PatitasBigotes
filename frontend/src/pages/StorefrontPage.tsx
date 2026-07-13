import { Link } from "react-router-dom";
import { formatArs, useStorefrontPage } from "../features/storefront";

export function StorefrontPage() {
  const storefront = useStorefrontPage();

  return (
    <section>
      <h1 className="page-title">Catalogo</h1>
      <p className="page-subtitle">Productos disponibles para mascotas.</p>

      <div className="categories-inline">
        <button
          type="button"
          className={storefront.selectedCategoryId === null ? "chip chip-selected" : "chip"}
          onClick={() => storefront.onCategoryClick(null)}
        >
          Todas
        </button>
        {storefront.categories.map((category) => (
          <button
            key={category.id}
            type="button"
            className={storefront.selectedCategoryId === category.id ? "chip chip-selected" : "chip"}
            onClick={() => storefront.onCategoryClick(category.id)}
          >
            {category.name}
          </button>
        ))}
      </div>

      <form className="search-row" onSubmit={storefront.onSubmit}>
        <input
          className="input"
          value={storefront.query}
          onChange={(event) => storefront.setQuery(event.target.value)}
          placeholder="Buscar por nombre..."
        />
        <button className="btn" type="submit">
          Buscar
        </button>
      </form>

      <div className="search-row storefront-filters-row">
        <label className="storefront-filter-field">
          Ordenar por
          <select
            className="input"
            value={storefront.sortBy}
            onChange={(event) => {
              storefront.setSortBy(event.target.value as "price" | "name");
              storefront.setPage(1);
            }}
          >
            <option value="price">Precio</option>
            <option value="name">Alfabetico</option>
          </select>
        </label>
        <label className="storefront-filter-field">
          Direccion
          <select
            className="input"
            value={storefront.sortDir}
            onChange={(event) => {
              storefront.setSortDir(event.target.value as "asc" | "desc");
              storefront.setPage(1);
            }}
          >
            <option value="asc">Ascendente</option>
            <option value="desc">Descendente</option>
          </select>
        </label>
        <label className="storefront-filter-field">
          Por pagina
          <select
            className="input"
            value={storefront.pageSize}
            onChange={(event) => {
              storefront.setPageSize(Number(event.target.value));
              storefront.setPage(1);
            }}
          >
            <option value={8}>8</option>
            <option value={12}>12</option>
            <option value={16}>16</option>
            <option value={24}>24</option>
          </select>
        </label>
      </div>

      {storefront.loading && <p>Cargando...</p>}
      {storefront.error && <p className="error">{storefront.error}</p>}
      {!storefront.loading && !storefront.error && storefront.products.length === 0 && (
        <p className="muted">No se encontraron productos para los filtros seleccionados.</p>
      )}
      <div className="products-grid products-grid-home">
        {storefront.products.map((product) => (
          <article className="card product-card-home" key={product.id}>
            {product.img_url ? (
              <img className="product-image product-image-home" src={product.img_url} alt={product.name} />
            ) : (
              <div className="image-placeholder">Sin imagen</div>
            )}
            <p className="category">{product.category_name ?? "Sin categoria"}</p>
            <h2>
              <Link className="product-title-link" to={`/products/${product.id}`}>
                {product.name}
              </Link>
            </h2>
            {product.has_discount && product.min_var_price_original !== null && product.min_var_price_original !== undefined ? (
              <p className="price">
                <span className="price-original">{formatArs(product.min_var_price_original)}</span>{" "}
                <span className="price-final">{formatArs(product.min_var_price_final ?? product.min_var_price)}</span>
              </p>
            ) : (
              <p className="price">{formatArs(product.min_var_price_final ?? product.min_var_price)}</p>
            )}
            {!product.in_stock && <p className="warning">Sin stock por ahora</p>}
          </article>
        ))}
      </div>

      {!storefront.loading && !storefront.error && (
        <div className="admin-inline-actions" style={{ marginTop: 16, justifyContent: "center" }}>
          <button
            className="btn btn-small btn-ghost"
            type="button"
            onClick={() => storefront.setPage((prev) => Math.max(1, prev - 1))}
            disabled={storefront.page <= 1}
            aria-label="Pagina anterior"
          >
            {"<"}
          </button>
          <p className="muted">
            Mostrando {storefront.pageInfo.from}-{storefront.pageInfo.to} de {storefront.total} | Pagina {storefront.page} / {storefront.totalPages}
          </p>
          <button
            className="btn btn-small btn-ghost"
            type="button"
            onClick={() => storefront.setPage((prev) => Math.min(storefront.totalPages, prev + 1))}
            disabled={storefront.page >= storefront.totalPages}
            aria-label="Pagina siguiente"
          >
            {">"}
          </button>
        </div>
      )}
    </section>
  );
}
