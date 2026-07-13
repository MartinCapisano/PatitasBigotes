import { Link } from "react-router-dom";
import { useCategoriesPage } from "../features/storefront";

export function CategoriesPage() {
  const categoriesPage = useCategoriesPage();

  return (
    <section>
      <h1 className="page-title">Categorias</h1>
      <p className="page-subtitle">Elegi una categoria para explorar productos.</p>

      {categoriesPage.loading && <p>Cargando...</p>}
      {categoriesPage.error && <p className="error">{categoriesPage.error}</p>}
      {!categoriesPage.loading && !categoriesPage.error && categoriesPage.categories.length === 0 && (
        <p className="muted">No hay categorias para mostrar.</p>
      )}

      <div className="admin-grid">
        {categoriesPage.categories.map((category) => (
          <article className="card" key={category.id}>
            <h2>{category.name}</h2>
            <p>Ver productos de esta categoria en la tienda.</p>
            <Link className="btn btn-small" to={`/home?category_id=${category.id}`}>
              Ver en home
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}
