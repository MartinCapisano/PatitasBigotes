from source.db.models import WebhookEvent


def create_webhook_event(db, *, event_key: str, status: str) -> None:
    db.add(
        WebhookEvent(
            provider="mercadopago",
            event_key=event_key,
            status=status,
            payload='{"type":"payment","data":{"id":"123"}}',
            last_error="boom" if status == "dead_letter" else None,
            attempt_count=3 if status == "dead_letter" else 1,
        )
    )
    db.commit()
