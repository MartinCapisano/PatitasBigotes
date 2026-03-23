from datetime import UTC, datetime

from source.db.models import User


def build_unique_email(*, prefix: str = "user") -> str:
    return f"{prefix}-{datetime.now(UTC).timestamp()}@example.com"


def create_user(
    db,
    *,
    first_name: str = "Jane",
    last_name: str = "Doe",
    email: str | None = None,
    email_prefix: str = "user",
    phone: str | None = None,
    password_hash: str = "!",
    has_account: bool = True,
    is_admin: bool = False,
    email_verified_at=None,
    token_version: int | None = None,
) -> User:
    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email or build_unique_email(prefix=email_prefix),
        phone=phone,
        password_hash=password_hash,
        has_account=has_account,
        is_admin=is_admin,
        email_verified_at=email_verified_at,
    )
    if token_version is not None:
        user.token_version = token_version
    db.add(user)
    db.flush()
    return user
