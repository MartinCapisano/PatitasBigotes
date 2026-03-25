import type { AdminSearchUser } from "../../../../services/admin-sales-api";

export function AdminUserSearchModal(props: {
  title: string;
  show: boolean;
  closeLabel?: string;
  onClose: () => void;
  searchFirstName: string;
  setSearchFirstName: (value: string) => void;
  searchLastName: string;
  setSearchLastName: (value: string) => void;
  searchEmail: string;
  setSearchEmail: (value: string) => void;
  searchDni: string;
  setSearchDni: (value: string) => void;
  searchPhone: string;
  setSearchPhone: (value: string) => void;
  searchLoading: boolean;
  searchError: string;
  searchResults: AdminSearchUser[];
  pendingSelectedUser: AdminSearchUser | null;
  onTogglePendingUser: (user: AdminSearchUser, checked: boolean) => void;
  onConfirmPendingUser: () => void;
}) {
  const {
    title,
    show,
    closeLabel = "X",
    onClose,
    searchFirstName,
    setSearchFirstName,
    searchLastName,
    setSearchLastName,
    searchEmail,
    setSearchEmail,
    searchDni,
    setSearchDni,
    searchPhone,
    setSearchPhone,
    searchLoading,
    searchError,
    searchResults,
    pendingSelectedUser,
    onTogglePendingUser,
    onConfirmPendingUser
  } = props;

  if (!show) return null;

  return (
    <div className="admin-modal-overlay" role="dialog" aria-modal="true">
      <div className="card admin-modal">
        <div className="admin-modal-header">
          <h3>{title}</h3>
          <button className="btn btn-small btn-ghost" type="button" onClick={onClose}>
            {closeLabel}
          </button>
        </div>
        <div className="admin-search-toolbar">
          <label className="admin-search-field">
            Nombre
            <input className="input" value={searchFirstName} onChange={(e) => setSearchFirstName(e.target.value)} />
          </label>
          <label className="admin-search-field">
            Apellido
            <input className="input" value={searchLastName} onChange={(e) => setSearchLastName(e.target.value)} />
          </label>
          <label className="admin-search-field">
            Email
            <input className="input" value={searchEmail} onChange={(e) => setSearchEmail(e.target.value)} />
          </label>
          <label className="admin-search-field">
            DNI
            <input className="input" value={searchDni} onChange={(e) => setSearchDni(e.target.value)} />
          </label>
          <label className="admin-search-field">
            Telefono
            <input className="input" value={searchPhone} onChange={(e) => setSearchPhone(e.target.value)} />
          </label>
        </div>
        {searchLoading ? <p className="muted">Buscando...</p> : null}
        {searchError ? <p className="error">{searchError}</p> : null}
        <div className="admin-scroll-list admin-search-results-list">
          {searchResults.map((user) => (
            <div className="admin-user-search-row" key={user.id}>
              <label className="admin-discount-product-check">
                <input
                  type="checkbox"
                  checked={pendingSelectedUser?.id === user.id}
                  onChange={(event) => onTogglePendingUser(user, event.target.checked)}
                />
                <span>
                  #{user.id} {user.first_name} {user.last_name}
                </span>
              </label>
              <p className="muted">Email: {user.email}</p>
              <p className="muted">DNI: {user.dni || "-"} | Tel: {user.phone || "-"}</p>
            </div>
          ))}
        </div>
        <p className="muted">
          {pendingSelectedUser
            ? `Seleccion temporal: #${pendingSelectedUser.id} - ${pendingSelectedUser.first_name} ${pendingSelectedUser.last_name} (${pendingSelectedUser.email})`
            : "Seleccion temporal: -"}
        </p>
        <div className="admin-inline-actions">
          <button className="btn btn-small" type="button" onClick={onConfirmPendingUser} disabled={!pendingSelectedUser}>
            Seleccionar
          </button>
        </div>
      </div>
    </div>
  );
}
