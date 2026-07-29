"""Add measure fields (sold_by, measure_unit, step) to product_variants.

Habilita la venta de productos por cantidad/peso (ver docs/products_by_measure.md).
Las variantes existentes quedan como `sold_by='unit'`, `step=1` gracias a los
server_default, por lo que la migración es segura sobre datos actuales.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260727_01"
down_revision = "20260718_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_variants",
        sa.Column("sold_by", sa.String(), nullable=False, server_default="unit"),
    )
    op.add_column(
        "product_variants",
        sa.Column("measure_unit", sa.String(), nullable=True),
    )
    op.add_column(
        "product_variants",
        sa.Column("step", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_product_variants_step_positive",
        "product_variants",
        "step > 0",
    )
    op.create_check_constraint(
        "ck_product_variants_sold_by_valid",
        "product_variants",
        "sold_by IN ('unit', 'measure')",
    )
    op.create_check_constraint(
        "ck_product_variants_measure_unit_present",
        "product_variants",
        "sold_by = 'unit' OR measure_unit IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_product_variants_measure_unit_present",
        "product_variants",
        type_="check",
    )
    op.drop_constraint(
        "ck_product_variants_sold_by_valid",
        "product_variants",
        type_="check",
    )
    op.drop_constraint(
        "ck_product_variants_step_positive",
        "product_variants",
        type_="check",
    )
    op.drop_column("product_variants", "step")
    op.drop_column("product_variants", "measure_unit")
    op.drop_column("product_variants", "sold_by")
