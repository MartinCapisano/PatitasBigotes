from source.db.models import Category, Product, ProductVariant

from tests.factories.orders import create_order_graph
from tests.factories.users import create_user


def create_catalog_with_variants(db) -> dict[str, int]:
    category = Category(name="Draft Cat")
    db.add(category)
    db.flush()

    product = Product(
        name="Draft Product",
        description="demo",
        category_id=int(category.id),
    )
    db.add(product)
    db.flush()

    variant_a = ProductVariant(
        product_id=int(product.id),
        sku="DRAFT-SKU-A",
        size="S",
        color="Blue",
        price=10000,
        stock=8,
        is_active=True,
    )
    variant_b = ProductVariant(
        product_id=int(product.id),
        sku="DRAFT-SKU-B",
        size="M",
        color="Red",
        price=15000,
        stock=6,
        is_active=True,
    )
    variant_inactive = ProductVariant(
        product_id=int(product.id),
        sku="DRAFT-SKU-C",
        size="L",
        color="Gray",
        price=20000,
        stock=5,
        is_active=False,
    )
    db.add_all([variant_a, variant_b, variant_inactive])
    db.commit()
    return {
        "variant_a": int(variant_a.id),
        "variant_b": int(variant_b.id),
        "variant_inactive": int(variant_inactive.id),
    }


def create_non_account_user(db) -> int:
    user = create_user(
        db,
        first_name="Ana",
        last_name="Buyer",
        email_prefix="buyer",
        phone="1144455566",
        has_account=False,
    )
    db.commit()
    return int(user.id)


def create_submitted_order_for_user(db, *, user_id: int) -> int:
    graph = create_order_graph(
        db,
        user_id=int(user_id),
        order_status="submitted",
        product_name="Order Product",
        sku_prefix="ORDER-SKU",
    )
    db.commit()
    return int(graph["order_id"])
