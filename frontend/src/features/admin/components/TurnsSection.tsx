import { useState } from "react";
import type { AdminTurn } from "../services";

export function TurnsSection(props: {
  turns: AdminTurn[];
  turnsError: string;
  turnsFilter: "all" | "pending" | "confirmed" | "cancelled";
  setTurnsFilter: (value: "all" | "pending" | "confirmed" | "cancelled") => void;
  loadTurns: () => Promise<void>;
  onUpdateTurnStatus: (turnId: number, status: "confirmed" | "cancelled") => Promise<void>;
}) {
  const { turns, turnsError, turnsFilter, setTurnsFilter, loadTurns, onUpdateTurnStatus } = props;
  const [expandedTurns, setExpandedTurns] = useState<Record<number, boolean>>({});
  const [openTurnMenuId, setOpenTurnMenuId] = useState<number | null>(null);

  function toggleTurnExpanded(turnId: number) {
    setExpandedTurns((prev) => ({ ...prev, [turnId]: !prev[turnId] }));
  }

  return (
    <article className="card admin-orders-section">
      <h2>Admin Turnos</h2>
      <div className="admin-inline-actions">
        <select
          className="input"
          value={turnsFilter}
          onChange={(e) => setTurnsFilter(e.target.value as "all" | "pending" | "confirmed" | "cancelled")}
        >
          <option value="all">Todos</option>
          <option value="pending">Pendientes</option>
          <option value="confirmed">Confirmados</option>
          <option value="cancelled">Cancelados</option>
        </select>
        <button className="btn btn-small" type="button" onClick={() => void loadTurns()}>
          Refrescar
        </button>
      </div>
      {turnsError && <p className="error">{turnsError}</p>}
      {turns.length === 0 ? (
        <p className="muted">No hay turnos para mostrar.</p>
      ) : (
        <div className="admin-products-list">
          <div className="admin-catalog-header">
            <p />
            <p>Cliente</p>
            <p>Telefono</p>
            <p>Horario</p>
            <p>Estado</p>
            <p>Acciones</p>
          </div>
          {turns.map((turn) => (
            <article className="card" key={turn.id}>
              <div className="admin-catalog-row">
                <button
                  className="admin-expand-btn"
                  type="button"
                  onClick={() => toggleTurnExpanded(turn.id)}
                  aria-label={expandedTurns[turn.id] ? "Contraer turno" : "Expandir turno"}
                >
                  {expandedTurns[turn.id] ? "v" : ">"}
                </button>
                <p>
                  <strong>{turn.customer.first_name || ""} {turn.customer.last_name || ""}</strong>
                </p>
                <p className="muted">{turn.customer.phone || "-"}</p>
                <p className="muted">{turn.notes || turn.scheduled_at || "-"}</p>
                <p className="muted">{turn.status}</p>
                <div className="admin-product-menu-wrap">
                  <button
                    className="btn btn-small btn-ghost"
                    type="button"
                    onClick={() => setOpenTurnMenuId((prev) => (prev === turn.id ? null : turn.id))}
                    aria-label="Opciones de turno"
                  >
                    ...
                  </button>
                  {openTurnMenuId === turn.id && (
                    <div className="admin-product-menu">
                      {turn.status === "pending" ? (
                        <>
                          <button className="btn btn-small btn-ghost" type="button" onClick={() => void onUpdateTurnStatus(turn.id, "confirmed")}>
                            Confirmar
                          </button>
                          <button className="btn btn-small btn-danger" type="button" onClick={() => void onUpdateTurnStatus(turn.id, "cancelled")}>
                            Cancelar
                          </button>
                        </>
                      ) : (
                        <p className="muted" style={{ margin: 0 }}>Sin acciones</p>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {expandedTurns[turn.id] ? (
                <div className="admin-variants-grid">
                  <div className="admin-variant-row">
                    <p><strong>ID:</strong> #{turn.id}</p>
                    <p className="muted"><strong>Cliente:</strong> #{turn.customer.id ?? "-"} </p>
                    <p className="muted"><strong>Fecha solicitada:</strong> {turn.scheduled_at ? new Date(turn.scheduled_at).toLocaleString() : "-"}</p>
                    <p className="muted"><strong>Notas:</strong> {turn.notes || "-"}</p>
                    <p className="muted"><strong>Creado:</strong> {new Date(turn.created_at).toLocaleString()}</p>
                    <p className="muted"><strong>Actualizado:</strong> {new Date(turn.updated_at).toLocaleString()}</p>
                  </div>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </article>
  );
}
