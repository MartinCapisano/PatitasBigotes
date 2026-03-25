import type { AdminCategory } from "../services";
import { AdminActionsMenu } from "./shared/AdminActionsMenu";
import { AdminExpandButton } from "./shared/AdminExpandButton";

export function CategoriesSection(props: {
  categories: AdminCategory[];
  productsCountByCategory: Record<string, number>;
  error: string;
  editingCategoryId: number | null;
  setEditingCategoryId: (value: number | null) => void;
  editCategoryName: string;
  setEditCategoryName: (value: string) => void;
  openCategoryMenuId: number | null;
  setOpenCategoryMenuId: (value: number | null | ((prev: number | null) => number | null)) => void;
  onStartCategoryEdit: (category: AdminCategory) => void;
  onSaveCategoryEdit: () => Promise<void>;
}) {
  const {
    categories,
    productsCountByCategory,
    error,
    editingCategoryId,
    setEditingCategoryId,
    editCategoryName,
    setEditCategoryName,
    openCategoryMenuId,
    setOpenCategoryMenuId,
    onStartCategoryEdit,
    onSaveCategoryEdit
  } = props;

  return (
    <article className="card admin-orders-section">
      <h2>Admin Categorias</h2>
      <p className="muted">Consulta y edita las categorias del catalogo sin salir del panel.</p>
      {error ? <p className="error">{error}</p> : null}
      {categories.length === 0 ? (
        <p className="muted">No hay categorias cargadas.</p>
      ) : (
        <div className="admin-products-list">
          <div className="admin-catalog-header">
            <p />
            <p>Categoria</p>
            <p>Productos</p>
            <p>Estado</p>
            <p>Acciones</p>
          </div>
          {categories.map((category) => {
            const expanded = editingCategoryId === category.id;
            const productsCount = productsCountByCategory[category.name] ?? 0;
            return (
              <article className="card" key={category.id}>
                <div className="admin-catalog-row">
                  <AdminExpandButton
                    expanded={expanded}
                    onToggle={() =>
                      expanded
                        ? setEditingCategoryId(null)
                        : onStartCategoryEdit(category)
                    }
                    expandLabel="Expandir categoria"
                    collapseLabel="Contraer categoria"
                  />
                  <p>
                    <strong>{category.name}</strong>
                  </p>
                  <p className="muted">{productsCount}</p>
                  <p className="muted">{productsCount > 0 ? "En uso" : "Disponible"}</p>
                  <AdminActionsMenu
                    isOpen={openCategoryMenuId === category.id}
                    onToggle={() => setOpenCategoryMenuId((prev) => (prev === category.id ? null : category.id))}
                    label="Opciones de categoria"
                  >
                    <button className="btn btn-small btn-ghost" type="button" onClick={() => onStartCategoryEdit(category)}>
                      Editar
                    </button>
                  </AdminActionsMenu>
                </div>

                {expanded ? (
                  <div className="admin-edit-box">
                    <h3>Editar categoria</h3>
                    <div className="admin-form-grid">
                      <label>
                        Nombre
                        <input
                          className="input"
                          value={editCategoryName}
                          onChange={(event) => setEditCategoryName(event.target.value)}
                        />
                      </label>
                    </div>
                    <div className="admin-product-actions">
                      <button className="btn btn-small" type="button" onClick={() => void onSaveCategoryEdit()}>
                        Guardar cambios
                      </button>
                      <button className="btn btn-small btn-ghost" type="button" onClick={() => setEditingCategoryId(null)}>
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </article>
  );
}
