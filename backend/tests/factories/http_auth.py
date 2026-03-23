def build_register_payload(
    *,
    first_name: str = "Ana",
    last_name: str = "Lopez",
    email: str = "ana@example.com",
    password: str = "Strong!123",
) -> dict[str, str]:
    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "password": password,
    }


def build_password_reset_request_payload(*, email: str) -> dict[str, str]:
    return {"email": email}


def build_password_change_payload(
    *,
    current_password: str,
    new_password: str,
) -> dict[str, str]:
    return {
        "current_password": current_password,
        "new_password": new_password,
    }
