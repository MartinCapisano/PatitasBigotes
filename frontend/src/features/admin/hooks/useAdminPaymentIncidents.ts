import { useEffect, useState } from "react";
import {
  listAdminPaymentIncidents,
  resolveAdminPaymentIncidentNoRefund,
  resolveAdminPaymentIncidentRefund,
  type AdminPaymentIncident
} from "../../../services/admin-orders-api";
import type { AdminSection } from "../types";

export function useAdminPaymentIncidents(params: { adminSection: AdminSection }) {
  const { adminSection } = params;
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [incidents, setIncidents] = useState<AdminPaymentIncident[]>([]);
  const [processingIncidentId, setProcessingIncidentId] = useState<number | null>(null);

  async function loadIncidents() {
    if (adminSection !== "incidencias_pago") return;
    setLoading(true);
    setError("");
    try {
      const rows = await listAdminPaymentIncidents({ status: "pending_review", limit: 200 });
      setIncidents(rows);
    } catch {
      setError("No se pudieron cargar las incidencias de pago.");
    } finally {
      setLoading(false);
    }
  }

  async function resolveWithRefund(incidentId: number, amount: number | undefined, reason: string) {
    const normalizedReason = reason.trim();
    if (!normalizedReason) {
      setError("El motivo del reembolso es obligatorio.");
      return;
    }
    setError("");
    setSuccess("");
    setProcessingIncidentId(incidentId);
    try {
      await resolveAdminPaymentIncidentRefund({
        incident_id: incidentId,
        amount,
        reason: normalizedReason
      });
      await loadIncidents();
      setSuccess(`Incidencia #${incidentId} resuelta con reembolso.`);
    } catch {
      setError("No se pudo resolver con reembolso.");
    } finally {
      setProcessingIncidentId(null);
    }
  }

  async function resolveWithoutRefund(incidentId: number, reason: string) {
    const normalizedReason = reason.trim();
    if (!normalizedReason) {
      setError("El motivo es obligatorio.");
      return;
    }
    setError("");
    setSuccess("");
    setProcessingIncidentId(incidentId);
    try {
      await resolveAdminPaymentIncidentNoRefund({
        incident_id: incidentId,
        reason: normalizedReason
      });
      await loadIncidents();
      setSuccess(`Incidencia #${incidentId} cerrada sin reembolso.`);
    } catch {
      setError("No se pudo cerrar la incidencia.");
    } finally {
      setProcessingIncidentId(null);
    }
  }

  useEffect(() => {
    void loadIncidents();
  }, [adminSection]);

  return {
    error,
    success,
    loading,
    incidents,
    resolveWithRefund,
    resolveWithoutRefund,
    processingIncidentId,
    reload: loadIncidents
  };
}
