from __future__ import annotations

from email.message import EmailMessage
import smtplib
from typing import TypedDict

from source.db.config import (
    get_mail_from,
    get_smtp_host,
    get_smtp_password,
    get_smtp_port,
    get_smtp_use_tls,
    get_smtp_username,
)


class OrderPaidEmailLineItem(TypedDict):
    product_name: str | None
    variant_label: str
    quantity: int
    line_total: int


class OrderPaidEmailPayload(TypedDict):
    to_email: str
    order_id: int
    order_status: str
    payment_id: int
    total_amount: int
    currency: str
    items: list[OrderPaidEmailLineItem]


class BankTransferInstructionsEmailPayload(TypedDict):
    to_email: str
    order_id: int
    payment_id: int
    amount: int
    currency: str
    deadline_hours: int
    alias: str
    cbu: str
    bank_name: str
    holder: str
    tax_id: str
    reference: str
    whatsapp_number: str
    whatsapp_url: str
    status_url: str


def _build_message(*, to_email: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = get_mail_from()
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def _send_message(msg: EmailMessage) -> None:
    host = get_smtp_host()
    port = get_smtp_port()
    username = get_smtp_username()
    password = get_smtp_password()
    use_tls = get_smtp_use_tls()

    with smtplib.SMTP(host=host, port=port, timeout=10) as smtp:
        if use_tls:
            smtp.starttls()
        if username:
            smtp.login(username, password)
        smtp.send_message(msg)


def send_email_verification(*, to_email: str, verify_link: str) -> None:
    body = (
        "Hola,\n\n"
        "Para verificar tu email en PatitasBigotes usa este enlace:\n"
        f"{verify_link}\n\n"
        "Si no solicitaste esta acción, ignorá este correo.\n"
    )
    msg = _build_message(
        to_email=to_email,
        subject="Verifica tu email",
        body=body,
    )
    _send_message(msg)


def send_password_reset(*, to_email: str, reset_link: str) -> None:
    body = (
        "Hola,\n\n"
        "Para restablecer tu contraseña en PatitasBigotes usa este enlace:\n"
        f"{reset_link}\n\n"
        "Si no solicitaste este cambio, ignorá este correo.\n"
    )
    msg = _build_message(
        to_email=to_email,
        subject="Restablecer contraseña",
        body=body,
    )
    _send_message(msg)


def _format_money(amount_cents: int, currency: str) -> str:
    whole = int(amount_cents) / 100
    return f"{currency} {whole:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def send_bank_transfer_instructions_email(
    *, payload: BankTransferInstructionsEmailPayload
) -> None:
    """The instructions in the customer's inbox, not just on a page they closed.

    Until this existed the only email of the payment cycle was the paid-order
    one, which arrives *after* the admin confirms -- long after the customer
    needed to know where to send the money.
    """
    order_id = int(payload["order_id"])
    reference = str(payload["reference"])
    currency = str(payload["currency"]).strip() or "ARS"
    deadline_hours = int(payload["deadline_hours"])

    body = (
        "Hola,\n\n"
        f"Recibimos tu orden #{order_id}. Para confirmarla necesitamos que hagas "
        "la transferencia con estos datos:\n\n"
        f"Monto exacto: {_format_money(int(payload['amount']), currency)}\n"
        f"Alias: {payload['alias']}\n"
        f"CBU: {payload['cbu']}\n"
        f"Banco: {payload['bank_name']}\n"
        f"Titular: {payload['holder']}\n"
        f"CUIT/CUIL: {payload['tax_id']}\n"
        f"Referencia: {reference}\n\n"
        f"Importante: pone la referencia {reference} en la transferencia. Es lo que "
        "nos permite reconocer tu pago.\n\n"
        f"Tenes {deadline_hours} hs para transferir, sino la orden se cancela.\n\n"
        f"Cuando transfieras, mandanos el comprobante por WhatsApp al "
        f"{payload['whatsapp_number']}:\n"
        f"{payload['whatsapp_url']}\n\n"
        "Podes volver a ver estos datos cuando quieras desde este enlace:\n"
        f"{payload['status_url']}\n\n"
        "Si tenes alguna duda, respondenos por nuestros canales de contacto.\n"
    )
    msg = _build_message(
        to_email=str(payload["to_email"]).strip(),
        subject=f"Datos para transferir - orden #{order_id}",
        body=body,
    )
    _send_message(msg)


def send_order_paid_email(*, payload: OrderPaidEmailPayload) -> None:
    order_id = int(payload["order_id"])
    payment_id = int(payload["payment_id"])
    order_status = str(payload["order_status"]).strip() or "paid"
    total_amount = int(payload["total_amount"])
    currency = str(payload["currency"]).strip() or "ARS"
    items = payload["items"]

    item_lines: list[str] = []
    for item in items:
        product_name = str(item.get("product_name") or f"Producto de la orden #{order_id}")
        variant_label = str(item.get("variant_label") or "-/-")
        quantity = int(item.get("quantity") or 0)
        line_total = int(item.get("line_total") or 0)
        item_lines.append(
            f"- {product_name} ({variant_label}) x {quantity}: {_format_money(line_total, currency)}"
        )

    item_block = "\n".join(item_lines) if item_lines else "- Sin items disponibles"
    body = (
        "Hola,\n\n"
        f"Tu orden #{order_id} fue actualizada.\n"
        f"Estado actual: {order_status}\n"
        f"Pago registrado: #{payment_id}\n"
        f"Total: {_format_money(total_amount, currency)}\n\n"
        "Detalle de la orden:\n"
        f"{item_block}\n\n"
        "Si tenes alguna duda, respondenos por nuestros canales de contacto.\n"
    )
    msg = _build_message(
        to_email=str(payload["to_email"]).strip(),
        subject=f"Actualizacion de tu orden #{order_id}",
        body=body,
    )
    _send_message(msg)
