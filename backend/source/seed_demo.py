from __future__ import annotations

import secrets
from datetime import UTC, datetime

from source.services.auth_security_s import hash_password
from source.db.config import get_app_env
from source.db.models import Category, Discount, Product, ProductVariant, User
from source.db.session import SessionLocal
from source.services.discount_s import create_discount, update_discount

DEMO_ADMIN_EMAIL = "admin@demo.com"
ALLOWED_SEED_ENVIRONMENTS = {"local", "demo"}

DEMO_CATALOG = [
    {
        "category": "Accesorios",
        "products": [
            {
                "name": "Collar Urban Paseo",
                "description": "Collar reforzado para uso diario.",
                "variants": [
                    {"sku": "DEMO-COLLAR-ROJO-S", "size": "S", "color": "Rojo", "price": 12990, "stock": 8},
                    {"sku": "DEMO-COLLAR-AZUL-M", "size": "M", "color": "Azul", "price": 14990, "stock": 6},
                ],
            },
            {
                "name": "Correa Confort Grip",
                "description": "Correa comoda con mango acolchado.",
                "variants": [
                    {"sku": "DEMO-CORREA-NEGRA-U", "size": "U", "color": "Negro", "price": 18990, "stock": 5},
                ],
            },
        ],
    },
    {
        "category": "Alimento",
        "products": [
            {
                "name": "Balanceado Adulto Premium",
                "description": "Alimento seco premium para perros adultos.",
                "variants": [
                    {"sku": "DEMO-BALANCEADO-3KG", "size": "3 kg", "color": None, "price": 25990, "stock": 10},
                    {"sku": "DEMO-BALANCEADO-10KG", "size": "10 kg", "color": None, "price": 68990, "stock": 4},
                ],
            },
            {
                "name": "Snack Dental Daily",
                "description": "Snack funcional para higiene dental diaria.",
                "variants": [
                    {"sku": "DEMO-SNACK-DENTAL-7", "size": "7 un", "color": None, "price": 9990, "stock": 12},
                ],
            },
        ],
    },
    {
        "category": "Higiene",
        "products": [
            {
                "name": "Shampoo Piel Sensible",
                "description": "Shampoo suave para banos frecuentes.",
                "variants": [
                    {"sku": "DEMO-SHAMPOO-250", "size": "250 ml", "color": None, "price": 13990, "stock": 7},
                ],
            },
        ],
    },
]


def _get_or_create_category(*, name: str, db) -> Category:
    category = db.query(Category).filter(Category.name == name).first()
    if category is None:
        category = Category(name=name)
        db.add(category)
        db.flush()
    return category


def _get_or_create_product(*, category_id: int, name: str, description: str | None, db) -> Product:
    product = (
        db.query(Product)
        .filter(Product.category_id == int(category_id), Product.name == name)
        .first()
    )
    if product is None:
        product = Product(
            category_id=int(category_id),
            name=name,
            description=description,
            img_url=None,
        )
        db.add(product)
        db.flush()
    else:
        product.description = description
    return product


def _upsert_variant(*, product_id: int, payload: dict, db) -> ProductVariant:
    variant = db.query(ProductVariant).filter(ProductVariant.sku == payload["sku"]).first()
    if variant is None:
        variant = ProductVariant(
            product_id=int(product_id),
            sku=payload["sku"],
            size=payload.get("size"),
            color=payload.get("color"),
            img_url=None,
            price=int(payload["price"]),
            stock=int(payload["stock"]),
            is_active=True,
        )
        db.add(variant)
        db.flush()
        return variant

    variant.product_id = int(product_id)
    variant.size = payload.get("size")
    variant.color = payload.get("color")
    variant.price = int(payload["price"])
    variant.stock = int(payload["stock"])
    variant.is_active = True
    return variant


def _ensure_demo_admin(*, db, password: str) -> User:
    admin = db.query(User).filter(User.email == DEMO_ADMIN_EMAIL).first()
    if admin is None:
        admin = User(
            first_name="Demo",
            last_name="Admin",
            email=DEMO_ADMIN_EMAIL,
            phone="1111111111",
            password_hash=hash_password(password),
            has_account=True,
            is_admin=True,
            email_verified_at=datetime.now(UTC),
            email_verification_sent_at=None,
        )
        db.add(admin)
        db.flush()
        return admin

    admin.first_name = "Demo"
    admin.last_name = "Admin"
    admin.phone = admin.phone or "1111111111"
    admin.password_hash = hash_password(password)
    admin.has_account = True
    admin.is_admin = True
    admin.email_verified_at = admin.email_verified_at or datetime.now(UTC)
    return admin


def _upsert_discount_by_name(*, name: str, payload: dict, db) -> dict:
    matches = db.query(Discount).filter(Discount.name == name).order_by(Discount.id.asc()).all()
    if not matches:
        return create_discount(payload, db=db)

    primary = matches[0]
    for duplicate in matches[1:]:
        db.delete(duplicate)
    db.flush()
    return update_discount(discount_id=int(primary.id), updates=payload, db=db) or payload


def seed_demo_data() -> None:
    app_env = get_app_env()
    if app_env not in ALLOWED_SEED_ENVIRONMENTS:
        raise RuntimeError(
            f"seed_demo_data solo puede correr con APP_ENV in {sorted(ALLOWED_SEED_ENVIRONMENTS)!r}, "
            f"pero APP_ENV='{app_env}'. Revisa backend/.env antes de continuar."
        )

    demo_admin_password = secrets.token_urlsafe(12)

    db = SessionLocal()
    try:
        admin = _ensure_demo_admin(db=db, password=demo_admin_password)

        categories: dict[str, Category] = {}
        products: dict[str, Product] = {}

        for category_payload in DEMO_CATALOG:
            category = _get_or_create_category(name=category_payload["category"], db=db)
            categories[category.name] = category

            for product_payload in category_payload["products"]:
                product = _get_or_create_product(
                    category_id=int(category.id),
                    name=product_payload["name"],
                    description=product_payload.get("description"),
                    db=db,
                )
                products[product.name] = product

                for variant_payload in product_payload["variants"]:
                    _upsert_variant(
                        product_id=int(product.id),
                        payload=variant_payload,
                        db=db,
                    )

        accesorios = categories["Accesorios"]
        snack_dental = products["Snack Dental Daily"]

        _upsert_discount_by_name(
            name="Demo 15% Accesorios",
            payload={
                "name": "Demo 15% Accesorios",
                "type": "percent",
                "value": 15,
                "scope": "category",
                "category_id": int(accesorios.id),
                "product_id": None,
                "is_active": True,
                "starts_at": None,
                "ends_at": None,
            },
            db=db,
        )
        _upsert_discount_by_name(
            name="Demo $12 Snack Dental",
            payload={
                "name": "Demo $12 Snack Dental",
                "type": "fixed",
                "value": 1200,
                "scope": "product",
                "category_id": None,
                "product_id": int(snack_dental.id),
                "is_active": True,
                "starts_at": None,
                "ends_at": None,
            },
            db=db,
        )

        db.commit()

        category_count = db.query(Category).count()
        product_count = db.query(Product).count()
        variant_count = db.query(ProductVariant).count()
        discount_count = db.query(Discount).count()

        print("Demo seed completed")
        print(f"Admin: {admin.email} / {demo_admin_password}")
        print("Guarda esta password ahora: no se vuelve a mostrar ni se guarda en el repo.")
        print(
            "Catalog:",
            f"{category_count} categories, {product_count} products, {variant_count} variants, {discount_count} discounts",
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
