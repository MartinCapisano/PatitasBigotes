"""Add public status token to payments."""

from __future__ import annotations

import secrets

from alembic import op
import sqlalchemy as sa


revision = "20260322_01"
down_revision = "20260321_01"
branch_labels = None
depends_on = None


payments_table = sa.table(
    "payments",
    sa.column("id", sa.Integer),
    sa.column("public_status_token", sa.String),
)


def _new_public_status_token() -> str:
    return secrets.token_urlsafe(32)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    payment_columns = {column["name"] for column in inspector.get_columns("payments")}

    if "public_status_token" not in payment_columns:
        with op.batch_alter_table("payments") as batch_op:
            batch_op.add_column(
                sa.Column("public_status_token", sa.String(), nullable=True)
            )

    rows = bind.execute(
        sa.select(payments_table.c.id).where(payments_table.c.public_status_token.is_(None))
    ).fetchall()

    generated_tokens: set[str] = set()
    for row in rows:
        token = _new_public_status_token()
        while token in generated_tokens:
            token = _new_public_status_token()
        generated_tokens.add(token)
        bind.execute(
            payments_table.update()
            .where(payments_table.c.id == row.id)
            .values(public_status_token=token)
        )

    payment_indexes = {index["name"] for index in inspector.get_indexes("payments")}
    if "ix_payments_public_status_token" not in payment_indexes:
        op.create_index(
            "ix_payments_public_status_token",
            "payments",
            ["public_status_token"],
            unique=True,
        )
    with op.batch_alter_table("payments") as batch_op:
        batch_op.alter_column("public_status_token", nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    payment_indexes = {index["name"] for index in inspector.get_indexes("payments")}
    payment_columns = {column["name"] for column in inspector.get_columns("payments")}
    if "ix_payments_public_status_token" in payment_indexes:
        op.drop_index("ix_payments_public_status_token", table_name="payments")
    if "public_status_token" in payment_columns:
        with op.batch_alter_table("payments") as batch_op:
            batch_op.drop_column("public_status_token")
