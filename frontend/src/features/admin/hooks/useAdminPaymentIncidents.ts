import { useState } from "react";
import {
  listAdminPaymentIncidents,
  resolveAdminPaymentIncidentNoRefund,
  resolveAdminPaymentIncidentRefund
} from "../../../services/admin-orders-api";
import { useAsyncResource } from "../../../lib/useAsyncResource";
import type { AdminSection } from "../types";

export function useAdminPaymentIncidents(params: { adminSection: AdminSection }) {
  const { adminSection } = params;
  const [success, setSuccess] = useState("");
  const [processingIncidentId, setProcessingIncidentId] = useState<number | null>(null);

  const {
    data: incidents,
    loading,
    error,
    setError,
    reload: loadIncidents
  } = useAsyncResource(() => listAdminPaymentIncidents({ status: "pending_review", limit: 200 }), [], {
    enabled: adminSection === "incidencias_pago",
    errorMessage: "No se pudieron cargar las incidencias de pago."
  });

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
