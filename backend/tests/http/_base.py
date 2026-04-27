import os
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "test-secret-http-fundamentals")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ISSUER", "patitasbigotes-api")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "120")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
os.environ.setdefault("APP_BASE_URL", "http://localhost:5173")
os.environ.setdefault(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
os.environ.setdefault("MERCADOPAGO_WEBHOOK_SECRET", "test-webhook-secret")

from auth.security import hash_password
from main import app
from source.db.models import Base, Category, Product, ProductVariant, User
from source.db.session import get_db, get_db_transactional


class HttpFundamentalsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=cls.engine,
        )
        Base.metadata.create_all(bind=cls.engine)

        def _get_db_override():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        def _get_db_transactional_override():
            db = cls.SessionLocal()
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        app.dependency_overrides[get_db] = _get_db_override
        app.dependency_overrides[get_db_transactional] = _get_db_transactional_override

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()

    @staticmethod
    def _origin_headers() -> dict[str, str]:
        return {"Origin": "http://localhost:5173"}

    def _db(self):
        return self.SessionLocal()

    def _create_user(
        self,
        *,
        email: str,
        password: str = "Strong!123",
        is_admin: bool = False,
        verified: bool = True,
    ) -> int:
        db = self._db()
        try:
            user = User(
                first_name="Test",
                last_name="User",
                email=email,
                phone="1122334455",
                password_hash=hash_password(password),
                has_account=True,
                is_admin=is_admin,
                email_verified_at=datetime.now(UTC) if verified else None,
            )
            db.add(user)
            db.commit()
            return int(user.id)
        finally:
            db.close()

    def _create_guest_user(
        self,
        *,
        email: str,
        first_name: str = "Guest",
        last_name: str = "User",
        phone: str = "11999888777",
    ) -> int:
        db = self._db()
        try:
            user = User(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                password_hash="!",
                has_account=False,
                is_admin=False,
                email_verified_at=None,
            )
            db.add(user)
            db.commit()
            return int(user.id)
        finally:
            db.close()

    def _seed_variant(self) -> int:
        db = self._db()
        try:
            category = Category(name="HTTP Cat")
            db.add(category)
            db.flush()

            product = Product(
                name="HTTP Product",
                description="demo",
                category_id=int(category.id),
            )
            db.add(product)
            db.flush()

            variant = ProductVariant(
                product_id=int(product.id),
                sku="HTTP-SKU-1",
                size="M",
                color="Blue",
                price=10000,
                stock=20,
                is_active=True,
            )
            db.add(variant)
            db.commit()
            return int(variant.id)
        finally:
            db.close()

    @staticmethod
    def _extract_token_from_mock(mocked_send, *, field: str) -> str:
        link = mocked_send.call_args.kwargs[field]
        return str(link).split("token=")[1]

    def _login(self, *, email: str, password: str = "Strong!123"):
        return self.client.post(
            "/auth/login",
            json={"email": email, "password": password},
            headers=self._origin_headers(),
        )
