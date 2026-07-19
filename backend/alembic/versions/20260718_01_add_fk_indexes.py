"""Add indexes to frequently-queried FK columns on orders, products and order_items."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260718_01"
down_revision = "20260322_01"
branch_labels = None
depends_on = None


INDEXES = [
    ("ix_orders_user_id", "orders", ["user_id"]),
    ("ix_products_category_id", "products", ["category_id"]),
    ("ix_order_items_order_id", "order_items", ["order_id"]),
    ("ix_order_items_product_id", "order_items", ["product_id"]),
    ("ix_order_items_variant_id", "order_items", ["variant_id"]),
    ("ix_order_items_discount_id", "order_items", ["discount_id"]),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for index_name, table_name, columns in INDEXES:
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for index_name, table_name, _columns in reversed(INDEXES):
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name=table_name)
