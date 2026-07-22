import { useCallback, useMemo, useState } from "react";
import {
  listAdminPendingBankTransfers,
  registerAdminOrderManualPayment,
  type AdminPendingBankTransfer
} from "../../../services/admin-orders-api";
import { toUserMessage } from "../../../services/http-errors";
import { useAsyncResource } from "../../../lib/useAsyncResource";
import { formatArs } from "../../../lib/money";
import { normalizePaymentAmountsForOrder } from "./useAdminRegisterPayment";
import type { AdminSection } from "../types";

/**
 * The admin side of the only online payment method there is.
 *
 * A transfer is verified by a human looking at their bank account, so this hook
 * exists to make that crossing cheap: the queue arrives oldest-first, each row
 * already knows the amount that must match, and confirming happens in place.
 */
export function useAdminBankTransfers(params: { adminSection: AdminSection }) {
  const { adminSection } = params;
  const [success, setSuccess] = useState("");
  const [confirmingPaymentId, setConfirmingPaymentId] = useState<number | null>(null);

  const {
    data: transfers,
    setData: setTransfers,
    loading,
    error,
    setError,
    reload
  } = useAsyncResource(() => listAdminPendingBankTransfers({ limit: 200 }), [], {
    enabled: adminSection === "transferencias",
    errorMessage: "No se pudieron cargar las transferencias pendientes."
  });

  /**
   * Oldest first, mirroring the server. The one that has waited longest is the
   * one whose reservation is closest to cancelling the order out from under the
   * customer, so it is the one that should be looked at first.
   */
  const sorted = useMemo(
    () => [...transfers].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at))),
    [transfers]
  );

  const confirmTransfer = useCallback(
    async (transfer: AdminPendingBankTransfer, receiptRef: string, receivedAmount: string) => {
      const normalizedRef = receiptRef.trim();
      if (!normalizedRef) {
        setSuccess("");
        setError("La referencia del comprobante es obligatoria.");
        return;
      }
      const expectedCents = Number(transfer.amount || 0);
      const normalized = normalizePaymentAmountsForOrder({
        paidRaw: receivedAmount,
        changeRaw: "0",
        totalCents: expectedCents,
        method: "bank_transfer"
      });
      if (!normalized) {
        setSuccess("");
        // Naming the expected number matters: the old message just said the
        // amount was invalid, leaving the admin to guess what it should be.
        setError(
          `El monto recibido no coincide con el total de la orden #${transfer.order_id}: tiene que ser ${formatArs(expectedCents)}.`
        );
        return;
      }

      setError("");
      setSuccess("");
      setConfirmingPaymentId(transfer.id);
      try {
        const result = await registerAdminOrderManualPayment({
          order_id: transfer.order_id,
          method: "bank_transfer",
          paid_amount: normalized.paidCents,
          payment_ref: normalizedRef
        });
        // The queue is "what still needs verifying": once confirmed, the row has
        // no business being there, and re-fetching to find that out would leave
        // it clickable in the meantime.
        setTransfers((previous) => previous.filter((row) => row.id !== transfer.id));
        setSuccess(
          `Transferencia confirmada. Orden #${result.order.id} ahora en estado ${result.order.status}.`
        );
      } catch (apiError: unknown) {
        setError(toUserMessage(apiError, "generic"));
      } finally {
        setConfirmingPaymentId(null);
      }
    },
    [setError, setTransfers]
  );

  return {
    transfers: sorted,
    loading,
    error,
    success,
    confirmingPaymentId,
    confirmTransfer,
    reload
  };
}
