import { useState } from "react";
import type { AdminPendingBankTransfer } from "../../../services/admin-orders-api";
import { formatAmountForInput } from "../../../lib/money";
import { formatReservationDeadline, formatWaiting } from "./transfer-clocks";

export function BankTransfersSection(props: {
  transfers: AdminPendingBankTransfer[];
  loading: boolean;
  error: string;
  success: string;
  confirmingPaymentId: number | null;
  confirmTransfer: (
    transfer: AdminPendingBankTransfer,
    receiptRef: string,
    receivedAmount: string
  ) => Promise<void>;
  reload: () => Promise<void>;
  formatArs: (cents: number | null) => string;
}) {
  const { transfers, loading, error, success, confirmingPaymentId, confirmTransfer, reload, formatArs } =
    props;
  const [refByPayment, setRefByPayment] = useState<Record<number, string>>({});
  const [amountByPayment, setAmountByPayment] = useState<Record<number, string>>({});

  return (
    <article className="card admin-orders-section">
      <h2>Transferencias pendientes</h2>
      <p className="muted">
        Cola de transferencias esperando verificacion. Chequea el dinero en la cuenta, cruza la referencia
        con el comprobante que llego por WhatsApp y confirma el pago desde aca.
      </p>
      <div className="admin-inline-actions">
        <button className="btn btn-small btn-ghost" type="button" onClick={() => void reload()}>
          Actualizar
        </button>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}
      {loading ? (
        <p>Cargando transferencias...</p>
      ) : transfers.length === 0 ? (
        <p className="muted">No hay transferencias pendientes.</p>
      ) : (
        <div className="admin-scroll-list">
          {transfers.map((transfer) => {
            const receiptRef = refByPayment[transfer.id] ?? "";
            // Prefilled with the exact amount so confirming a correct transfer
            // is one click, and a mismatch is something the admin edits on
            // purpose instead of retyping from memory.
            const receivedAmount = amountByPayment[transfer.id] ?? formatAmountForInput(transfer.amount);
            const isConfirmingThis = confirmingPaymentId === transfer.id;
            const anyConfirming = confirmingPaymentId !== null;
            return (
              <div className="admin-variant-row" key={transfer.id}>
                <p>
                  <strong>{transfer.reference}</strong>
                </p>
                <p className="muted">
                  Orden #{transfer.order_id} | Pago #{transfer.id} | Monto exacto: {formatArs(transfer.amount)}
                </p>
                <p className="muted">
                  Cliente:{" "}
                  {transfer.customer
                    ? `${transfer.customer.first_name} ${transfer.customer.last_name} (${transfer.customer.email})`
                    : "-"}
                </p>
                <p className="muted">
                  Esperando {formatWaiting(transfer.created_at)} | Reserva de stock:{" "}
                  {formatReservationDeadline(transfer.reservation_expires_at)}
                </p>

                <div className="admin-form-grid">
                  <label>
                    Monto recibido (ARS)
                    <input
                      className="input"
                      type="text"
                      inputMode="decimal"
                      value={receivedAmount}
                      onChange={(event) =>
                        setAmountByPayment((prev) => ({
                          ...prev,
                          [transfer.id]: event.target.value
                        }))
                      }
                    />
                  </label>
                  <label>
                    Referencia del comprobante
                    <input
                      className="input"
                      value={receiptRef}
                      onChange={(event) =>
                        setRefByPayment((prev) => ({
                          ...prev,
                          [transfer.id]: event.target.value
                        }))
                      }
                      placeholder="Nro. de operacion del comprobante"
                    />
                  </label>
                </div>

                <div className="admin-product-actions">
                  <button
                    className="btn btn-small"
                    type="button"
                    disabled={anyConfirming}
                    onClick={() => void confirmTransfer(transfer, receiptRef, receivedAmount)}
                  >
                    {isConfirmingThis ? "Confirmando..." : "Confirmar pago"}
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
