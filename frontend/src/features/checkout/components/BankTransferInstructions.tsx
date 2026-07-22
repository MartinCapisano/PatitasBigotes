import { Link } from "react-router-dom";
import { useCopyToClipboard } from "../hooks/useCopyToClipboard";
import { buildBankTransferStatusUrl } from "../../../lib/bank-transfer";
import { formatArs } from "../../../lib/money";
import type { BankTransferInstructions as Instructions } from "../../../types";

/**
 * Hours the customer is promised to transfer within.
 *
 * Must stay well under the stock reservation window (42 h), which is what
 * actually cancels the order: promising more than the reservation guarantees
 * would mean cancelling orders before the deadline we gave.
 */
export const TRANSFER_DEADLINE_HOURS = 24;

type CopyableRowProps = {
  label: string;
  value: string;
  copyKey: string;
  copy: (key: string, value: string) => Promise<void>;
  copyState: "copied" | "failed" | null;
};

function CopyableRow({ label, value, copyKey, copy, copyState }: CopyableRowProps) {
  return (
    <div className="transfer-row">
      <div className="transfer-row-main">
        <span className="transfer-label">{label}</span>
        <span className="transfer-value">{value}</span>
      </div>
      <div className="transfer-row-side">
        <button
          className="btn btn-small btn-ghost"
          type="button"
          onClick={() => void copy(copyKey, value)}
          aria-label={`Copiar ${label}`}
        >
          Copiar
        </button>
        <span className="transfer-copy-status" role="status">
          {copyState === "copied" && <span className="success">Copiado</span>}
          {copyState === "failed" && (
            <span className="error">No se pudo copiar, copialo a mano</span>
          )}
        </span>
      </div>
    </div>
  );
}

function PlainRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="transfer-row">
      <div className="transfer-row-main">
        <span className="transfer-label">{label}</span>
        <span className="transfer-value">{value}</span>
      </div>
    </div>
  );
}

type Props = {
  orderId: number;
  instructions: Instructions;
  /** When given, offers the link back to these instructions. A guest has no
   *  account, so without it closing the tab loses the data for good. */
  publicStatusToken?: string | null;
};

export function BankTransferInstructions({ orderId, instructions, publicStatusToken }: Props) {
  const { copy, stateFor } = useCopyToClipboard();
  const statusUrl = publicStatusToken
    ? buildBankTransferStatusUrl(publicStatusToken, window.location.origin)
    : null;

  return (
    <div className="card transfer-card">
      <h2>Ya casi: ahora transferí</h2>
      <p className="muted">
        Guardamos tu orden #{orderId} y reservamos el stock. Se confirma cuando recibamos
        la transferencia.
      </p>

      <p className="transfer-deadline error">
        Tenés {TRANSFER_DEADLINE_HOURS} hs para transferir, sino la orden se cancela.
      </p>

      <div className="transfer-amount-block">
        <span className="transfer-label">Monto exacto a transferir</span>
        <p className="checkout-total">{formatArs(instructions.amount)}</p>
      </div>

      <div className="transfer-data">
        <CopyableRow
          label="Alias"
          value={instructions.alias}
          copyKey="alias"
          copy={copy}
          copyState={stateFor("alias")}
        />
        <CopyableRow
          label="CBU"
          value={instructions.cbu}
          copyKey="cbu"
          copy={copy}
          copyState={stateFor("cbu")}
        />
        <PlainRow label="Banco" value={instructions.bank_name} />
        <PlainRow label="Titular" value={instructions.holder} />
        <PlainRow label="CUIT / CUIL" value={instructions.tax_id} />
        <CopyableRow
          label="Referencia"
          value={instructions.reference}
          copyKey="reference"
          copy={copy}
          copyState={stateFor("reference")}
        />
      </div>

      <p className="muted">
        Poné la referencia <strong>{instructions.reference}</strong> en la transferencia:
        es lo que nos permite reconocer tu pago.
      </p>

      <div className="checkout-actions">
        <a
          className="btn"
          href={instructions.whatsapp_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Enviar el comprobante por WhatsApp
        </a>
      </div>
      <p className="muted">
        Mandanos el comprobante por WhatsApp al {instructions.whatsapp_number} y confirmamos
        tu compra apenas verifiquemos el pago.
      </p>

      {statusUrl && (
        <div className="transfer-keep-link">
          <p className="muted">
            <strong>Guardate este enlace</strong> para volver a estos datos cuando cierres la
            pagina:
          </p>
          <CopyableRow
            label="Enlace"
            value={statusUrl}
            copyKey="status-url"
            copy={copy}
            copyState={stateFor("status-url")}
          />
        </div>
      )}

      <div className="checkout-actions">
        <Link className="btn btn-small btn-ghost" to="/home">
          Volver a la tienda
        </Link>
      </div>
    </div>
  );
}
