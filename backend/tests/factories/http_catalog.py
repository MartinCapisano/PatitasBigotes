from source.db.models import Category, Product, ProductVariant


def create_catalog(db) -> dict[str, int]:
    cat_a = Category(name="Accesorios")
    cat_b = Category(name="Alimento")
    db.add_all([cat_a, cat_b])
    db.flush()

    p1 = Product(name="Collar A", description="d1", category_id=int(cat_a.id))
    p2 = Product(name="Correa B", description="d2", category_id=int(cat_a.id))
    p3 = Product(name="Comida C", description="d3", category_id=int(cat_b.id))
    db.add_all([p1, p2, p3])
    db.flush()

    db.add_all(
        [
            ProductVariant(
                product_id=int(p1.id),
                sku="SKU-A1",
                size="S",
                color="Red",
                price=10000,
                stock=2,
                is_active=True,
            ),
            ProductVariant(
                product_id=int(p1.id),
                sku="SKU-A2",
                size="M",
                color="Blue",
                price=12000,
                stock=0,
                is_active=False,
            ),
            ProductVariant(
                product_id=int(p2.id),
                sku="SKU-B1",
                size="U",
                color="Black",
                price=25000,
                stock=0,
                is_active=True,
            ),
            ProductVariant(
                product_id=int(p3.id),
                sku="SKU-C1",
                size="L",
                color="Green",
                price=40000,
                stock=5,
                is_active=True,
            ),
        ]
    )
    db.commit()
    return {
        "category_a": int(cat_a.id),
        "category_b": int(cat_b.id),
        "product_1": int(p1.id),
        "product_2": int(p2.id),
        "product_3": int(p3.id),
    }


def create_hidden_product(db) -> int:
    hidden_category = Category(name="Hidden")
    db.add(hidden_category)
    db.flush()

    hidden_product = Product(
        name="Hidden Product",
        description="hidden",
        category_id=int(hidden_category.id),
    )
    db.add(hidden_product)
    db.flush()

    db.add(
        ProductVariant(
            product_id=int(hidden_product.id),
            sku="SKU-HIDDEN-1",
            size="U",
            color="Gray",
            price=9000,
            stock=3,
            is_active=False,
        )
    )
    db.commit()
    return int(hidden_product.id)
