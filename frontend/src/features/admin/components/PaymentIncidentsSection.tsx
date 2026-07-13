import { useMemo, useState } from "react";
import type { AdminPaymentIncident } from "../services";

function getRecommendation(incident: AdminPaymentIncident): string {
  const orderStatus = incident.order.status;
  if (orderStatus === "cancelled") {
    return "Recomendado: reembolsar. El pago llego para una orden cancelada.";
  }
  if (orderStatus === "paid") {
    return "Recomendado: validar duplicidad y reembolsar si ya se cobro por otro medio.";
  }
  return "Revisar manualmente el caso antes de decidir.";
}

export function PaymentIncidentsSection(props: {
  error: string;
  success: string;
  loading: boolean;
  incidents: AdminPaymentIncident[];
  resolveWithRefund: (incidentId: number, amount: number | undefined, reason: string) => Promise<void>;
  resolveWithoutRefund: (incidentId: number, reason: string) => Promise<void>;
  processingIncidentId: number | null;
  formatArs: (cents: number | null) => string;
}) {
  const { error, success, loading, incidents, resolveWithRefund, resolveWithoutRefund, processingIncidentId, formatArs } = props;
  const [reasonByIncident, setReasonByIncident] = useState<Record<number, string>>({});
  const [amountByIncident, setAmountByIncident] = useState<Record<number, string>>({});

  const sorted = useMemo(
    () => [...incidents].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))),
    [incidents]
  );

  return (
    <article className="card admin-orders-section">
      <h2>Incidencias de pago</h2>
      <p className="muted">Casos de pago tardio/duplicado para decidir reembolso con evidencia visible.</p>
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}
      {loading ? (
        <p>Cargando incidencias...</p>
      ) : sorted.length === 0 ? (
        <p className="muted">Sin incidencias pendientes.</p>
      ) : (
        <div className="admin-scroll-list">
          {sorted.map((incident) => {
            const reason = reasonByIncident[incident.id] ?? "";
            const amountRaw = amountByIncident[incident.id] ?? "";
            const parsedAmount = amountRaw.trim() ? Number.parseInt(amountRaw, 10) : undefined;
            const isProcessingThis = processingIncidentId === incident.id;
            const anyProcessing = processingIncidentId !== null;
            return (
              <div className="admin-variant-row" key={incident.id}>
                <p>
                  <strong>Incidencia #{incident.id}</strong> | Tipo: {incident.type}
                </p>
                <p className="muted">Estado incidencia: {incident.status}</p>
                <p className="muted">
                  Orden #{incident.order_id} ({incident.order.status || "-"}) | Pago #{incident.payment_id} ({incident.payment.method || "-"} /{" "}
                  {incident.payment.status || "-"})
                </p>
                <p className="muted">
                  Monto pago: {formatArs(incident.payment.amount)} | Ref: {incident.payment.external_ref || "-"}
                </p>
                <p className="muted">Fecha deteccion: {new Date(incident.created_at).toLocaleString()}</p>
                <p className="muted">{getRecommendation(incident)}</p>
                <p className="muted">Motivo tecnico: {incident.reason || "-"}</p>

                <div className="admin-form-grid">
                  <label>
                    Motivo de decision
                    <input
                      className="input"
                      value={reason}
                      onChange={(event) =>
                        setReasonByIncident((prev) => ({
                          ...prev,
                          [incident.id]: event.target.value
                        }))
                      }
                      placeholder="Ej: pago tardio confirmado, se devuelve total"
                    />
                  </label>
                  <label>
                    Monto a reembolsar (centavos, vacio = total)
                    <input
                      className="input"
                      type="number"
                      min={1}
                      value={amountRaw}
                      onChange={(event) =>
                        setAmountByIncident((prev) => ({
                          ...prev,
                          [incident.id]: event.target.value
                        }))
                      }
                      placeholder={String(incident.payment.amount ?? "")}
                    />
                  </label>
                </div>

                <div className="admin-product-actions">
                  <button
                    className="btn btn-small"
                    type="button"
                    disabled={anyProcessing}
                    onClick={() =>
                      void resolveWithRefund(
                        incident.id,
                        Number.isNaN(parsedAmount ?? NaN) ? undefined : parsedAmount,
                        reason
                      )
                    }
                  >
                    {isProcessingThis ? "Procesando..." : "Resolver con reembolso"}
                  </button>
                  <button
                    className="btn btn-small btn-ghost"
                    type="button"
                    disabled={anyProcessing}
                    onClick={() => void resolveWithoutRefund(incident.id, reason)}
                  >
                    {isProcessingThis ? "Procesando..." : "Cerrar sin reembolso"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </article>
  );
}
