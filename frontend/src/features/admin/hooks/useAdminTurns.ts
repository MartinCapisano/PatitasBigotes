import { useState } from "react";
import { listAdminTurns, updateAdminTurnStatus } from "../../../services/turns-api";
import { useAsyncResource } from "../../../lib/useAsyncResource";
import type { AdminSection } from "../types";

export function useAdminTurns(adminSection: AdminSection) {
  const [turnsFilter, setTurnsFilter] = useState<"all" | "pending" | "confirmed" | "cancelled">("all");

  const {
    data: turns,
    error: turnsError,
    setError: setTurnsError,
    reload: loadTurns
  } = useAsyncResource(() => listAdminTurns(turnsFilter === "all" ? undefined : turnsFilter), [], {
    enabled: adminSection === "turnos",
    deps: [turnsFilter],
    errorMessage: "No se pudieron cargar los turnos."
  });

  async function onUpdateTurnStatus(turnId: number, status: "confirmed" | "cancelled") {
    setTurnsError("");
    try {
      await updateAdminTurnStatus(turnId, status);
      await loadTurns();
    } catch {
      setTurnsError("No se pudo actualizar el estado del turno.");
    }
  }

  return {
    turns,
    turnsFilter,
    setTurnsFilter,
    turnsError,
    loadTurns,
    onUpdateTurnStatus
  };
}
