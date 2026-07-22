"""Instrucciones de transferencia: todo lo que el cliente necesita para pagar.

Transferencia bancaria es el único método de pago online, y su "integración con
el proveedor" es un humano leyendo datos en una pantalla. Este módulo es el
equivalente de `payment_provider_s` para ese camino: arma el payload que ve el
cliente -- datos de la cuenta, referencia de la orden y el enlace de WhatsApp
por donde manda el comprobante.

Vive fuera del kernel (`payment_core_s`) porque no lo comparten todos los
caminos de pago: es específico de `bank_transfer`. La pantalla del checkout, la
re-visita desde "Mi cuenta" y el email de instrucciones tienen que decir todos
lo mismo, así que la copia y el enlace se arman en un solo lugar.
"""
from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from sqlalchemy.orm import Session, joinedload

from source.db.config import (
    get_app_base_url,
    get_bank_transfer_alias,
    get_bank_transfer_bank_name,
    get_bank_transfer_cbu,
    get_bank_transfer_cuit,
    get_bank_transfer_holder,
    get_whatsapp_number,
)
from source.db.models import Order, OrderItem, Payment, variant_label
from source.services.payment_core_s import deserialize_provider_payload
from source.services.stock_reservations_s import expire_active_reservations_for_order

WHATSAPP_BASE_URL = "https://wa.me"

TRANSFER_DEADLINE_HOURS = 24
"""Hours the customer is promised to transfer within.

Must stay well under the stock reservation window (42 h), which is what
actually cancels the order: promising more than the reservation guarantees
would mean cancelling orders before the deadline we gave. The checkout screen
states the same number.
"""


def build_payment_reference(order_id: int, payment_id: int) -> str:
    """The string that lets the admin match a WhatsApp message to an order.

    It is the only link between the money landing in the bank account and the
    order it pays for: there is no webhook, so this is what a human cross-checks.
    """
    return f"ORDER-{int(order_id)}-PAY-{int(payment_id)}"


def build_whatsapp_receipt_url(reference: str) -> str:
    """A wa.me link that opens the chat with the receipt message already written.

    The reference travels inside the message so the customer cannot forget to
    include it -- the whole manual verification depends on it being there.
    """
    message = (
        "Hola! Te envío el comprobante de mi transferencia. "
        f"Referencia: {reference}"
    )
    return f"{WHATSAPP_BASE_URL}/{get_whatsapp_number()}?text={quote(message)}"


def build_bank_transfer_payload(
    order_id: int,
    payment_id: int,
    amount: int,
    currency: str,
) -> dict:
    reference = build_payment_reference(order_id, payment_id)
    return {
        "instructions": {
            "alias": get_bank_transfer_alias(),
            "cbu": get_bank_transfer_cbu(),
            "bank_name": get_bank_transfer_bank_name(),
            "holder": get_bank_transfer_holder(),
            "tax_id": get_bank_transfer_cuit(),
            "reference": reference,
            "amount": amount,
            "currency": currency,
            "whatsapp_number": get_whatsapp_number(),
            "whatsapp_url": build_whatsapp_receipt_url(reference),
        }
    }


def build_status_url(public_status_token: str) -> str:
    """The link that reopens the instructions with no login. Mirrors the SPA route."""
    return f"{get_app_base_url()}/transferencia?token={quote(public_status_token, safe='')}"


def build_instructions_email_payload(
    *,
    to_email: str,
    order_id: int,
    payment_id: int,
    instructions: dict,
    public_status_token: str,
) -> dict:
    """Turns the stored instructions into what the email needs.

    Reads the payload the payment already carries rather than rebuilding it, so
    the email, the checkout screen and the guest's link cannot disagree about
    the account a customer is being told to pay into.
    """
    return {
        "to_email": to_email,
        "order_id": int(order_id),
        "payment_id": int(payment_id),
        "amount": int(instructions["amount"]),
        "currency": str(instructions["currency"]),
        "deadline_hours": TRANSFER_DEADLINE_HOURS,
        "alias": str(instructions["alias"]),
        "cbu": str(instructions["cbu"]),
        "bank_name": str(instructions["bank_name"]),
        "holder": str(instructions["holder"]),
        "tax_id": str(instructions["tax_id"]),
        "reference": str(instructions["reference"]),
        "whatsapp_number": str(instructions["whatsapp_number"]),
        "whatsapp_url": str(instructions["whatsapp_url"]),
        "status_url": build_status_url(public_status_token),
    }


def get_public_bank_transfer_status(
    *,
    public_status_token: str | None,
    db: Session,
) -> dict:
    """What a customer sees when they come back to their transfer link.

    The token is the capability: guests have no account, so this is the only way
    they can reach their own instructions after closing the tab. It reads the
    payload stored when the payment was created, which is exactly what the
    checkout screen showed and what the email will repeat -- one payment, one
    set of instructions.

    Instructions come back only while the transfer is still worth making.
    Handing them to someone whose order was already paid or cancelled would be
    inviting a second transfer nobody can match to anything.
    """
    normalized_token = str(public_status_token or "").strip()
    if not normalized_token:
        raise ValueError("public_status_token is required")
    if len(normalized_token) > 255:
        raise ValueError("public_status_token is too long")

    payment = (
        db.query(Payment)
        .options(
            joinedload(Payment.order).joinedload(Order.items).joinedload(OrderItem.product),
            joinedload(Payment.order).joinedload(Order.items).joinedload(OrderItem.variant),
        )
        .filter(
            Payment.method == "bank_transfer",
            Payment.public_status_token == normalized_token,
        )
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .first()
    )
    if payment is None:
        raise LookupError("payment not found")

    order = payment.order
    if order is None:
        raise LookupError("order not found")

    # Sweep first: an order whose reservation already lapsed is about to be
    # cancelled, and telling its owner to go transfer would be sending them
    # after money we are about to refuse.
    expire_active_reservations_for_order(
        order_id=int(order.id),
        now=datetime.now(UTC),
        db=db,
    )
    db.refresh(order)
    db.refresh(payment)

    order_status = str(order.status)
    payment_status = str(payment.status)
    can_pay = order_status == "submitted" and payment_status == "pending"

    instructions = None
    if can_pay:
        stored_payload = deserialize_provider_payload(payment.provider_payload) or {}
        instructions = stored_payload.get("instructions")

    return {
        "order_id": int(order.id),
        "order_status": order_status,
        "order_total": int(order.total_amount or 0),
        "currency": str(order.currency or "ARS"),
        # What they bought, so someone with more than one pending order can tell
        # which transfer this screen is asking for. Same shape the MercadoPago
        # snapshot returns, so both public views describe an order alike.
        "items": [
            {
                "product_name": item.product.name if item.product is not None else None,
                "variant_label": variant_label(item.variant),
                "quantity": int(item.quantity),
                "line_total": int(item.line_total or 0),
            }
            for item in sorted(order.items, key=lambda row: row.id)
        ],
        "payment_id": int(payment.id),
        "payment_status": payment_status,
        "can_pay": can_pay,
        "instructions": instructions,
    }
