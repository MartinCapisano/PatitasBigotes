from __future__ import annotations

from pathlib import Path
import mimetypes
import os
from urllib.parse import urlsplit
import uuid

from fastapi import UploadFile

from source.db.config import (
    get_payment_receipts_base_url,
    get_payment_receipts_dir,
)

ALLOWED_RECEIPT_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/pdf": ".pdf",
}
ALLOWED_RECEIPT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_RECEIPT_SIZE_BYTES = 10 * 1024 * 1024


def _ensure_receipts_dir() -> Path:
    directory = Path(get_payment_receipts_dir()).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    return directory.resolve()


def _safe_original_filename(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "receipt"
    return Path(raw).name.replace("\x00", "").strip() or "receipt"


def _validate_receipt_extension(*, filename: str, content_type: str) -> str:
    suffix = Path(filename).suffix.strip().lower()
    if suffix not in ALLOWED_RECEIPT_EXTENSIONS:
        raise ValueError("receipt file extension is not allowed")

    expected_suffix = ALLOWED_RECEIPT_CONTENT_TYPES.get(content_type)
    if expected_suffix is None:
        raise ValueError("receipt file content type is not allowed")
    if expected_suffix == ".jpg" and suffix in {".jpg", ".jpeg"}:
        return ".jpg"
    if suffix != expected_suffix:
        raise ValueError("receipt file extension does not match content type")
    return suffix


def build_receipt_url(stored_filename: str) -> str:
    normalized = str(stored_filename or "").strip()
    if not normalized or "/" in normalized or "\\" in normalized:
        raise ValueError("invalid stored receipt filename")
    return f"{get_payment_receipts_base_url()}/{normalized}"


def extract_managed_receipt_filename(receipt_url: str | None) -> str | None:
    normalized_url = str(receipt_url or "").strip()
    if not normalized_url:
        return None
    base_url = get_payment_receipts_base_url()
    prefix = f"{base_url}/"
    if not normalized_url.startswith(prefix):
        return None
    candidate = normalized_url[len(prefix):].strip()
    if not candidate or "/" in candidate or "\\" in candidate:
        return None
    return candidate


def save_receipt_upload(*, payment_id: int, file: UploadFile) -> dict:
    original_filename = _safe_original_filename(file.filename)
    content_type = str(file.content_type or "").strip().lower()
    if not content_type:
        raise ValueError("receipt file content type is required")
    normalized_extension = _validate_receipt_extension(
        filename=original_filename,
        content_type=content_type,
    )

    content = file.file.read()
    if not content:
        raise ValueError("receipt file is empty")
    if len(content) > MAX_RECEIPT_SIZE_BYTES:
        raise ValueError("receipt file exceeds the maximum allowed size")

    stored_filename = f"payment-{int(payment_id)}-{uuid.uuid4().hex}{normalized_extension}"
    receipts_dir = _ensure_receipts_dir()
    destination = (receipts_dir / stored_filename).resolve()
    if destination.parent != receipts_dir:
        raise ValueError("invalid receipt destination")

    destination.write_bytes(content)
    return {
        "url": build_receipt_url(stored_filename),
        "stored_filename": stored_filename,
        "original_filename": original_filename,
        "content_type": content_type,
        "size_bytes": len(content),
        "path": destination,
    }


def delete_stored_receipt_by_filename(stored_filename: str | None) -> None:
    normalized = str(stored_filename or "").strip()
    if not normalized or "/" in normalized or "\\" in normalized:
        return
    receipts_dir = _ensure_receipts_dir()
    target = (receipts_dir / normalized).resolve()
    if target.parent != receipts_dir:
        return
    try:
        target.unlink(missing_ok=True)
    except OSError:
        return


def resolve_receipt_path(stored_filename: str) -> tuple[Path, str | None]:
    normalized = str(stored_filename or "").strip()
    if not normalized or "/" in normalized or "\\" in normalized:
        raise LookupError("receipt not found")
    receipts_dir = _ensure_receipts_dir()
    target = (receipts_dir / normalized).resolve()
    if target.parent != receipts_dir or not target.is_file():
        raise LookupError("receipt not found")
    media_type, _ = mimetypes.guess_type(target.name)
    return target, media_type
