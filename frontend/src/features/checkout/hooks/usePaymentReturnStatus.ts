import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { fetchPublicPaymentStatus, type PublicPaymentStatus } from "../../../services/payments-api";

export function usePaymentReturnStatus() {
  const location = useLocation();
  const [status, setStatus] = useState<PublicPaymentStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const lookup = useMemo(
    () => ({
      publicStatusToken: params.get("public_status_token"),
    }),
    [params]
  );

  async function loadStatus() {
    if (!lookup.publicStatusToken) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payment = await fetchPublicPaymentStatus(lookup);
      setStatus(payment);
    } catch {
      setError("No se pudo consultar el estado actualizado del pago.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadStatus();
  }, [lookup.publicStatusToken]);

  return {
    location,
    status,
    loading,
    error,
    loadStatus
  };
}
