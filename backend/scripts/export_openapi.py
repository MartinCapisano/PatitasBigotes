"""Dump the FastAPI app's OpenAPI schema to a JSON file, without needing a running server or a real database.

Used to keep the frontend's generated TypeScript types (frontend/src/types/api.generated.ts)
in sync with the backend's actual request/response contract.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "openapi-export")
os.environ.setdefault("MERCADOPAGO_WEBHOOK_SECRET", "openapi-export")

# The app refuses to boot without the shop's bank details (it could not be paid
# without them). Dumping a schema is not taking payments, so stub them out the
# same way as the database above.
os.environ.setdefault("BANK_TRANSFER_ALIAS", "openapi-export")
os.environ.setdefault("BANK_TRANSFER_CBU", "openapi-export")
os.environ.setdefault("BANK_TRANSFER_BANK_NAME", "openapi-export")
os.environ.setdefault("BANK_TRANSFER_HOLDER", "openapi-export")
os.environ.setdefault("BANK_TRANSFER_CUIT", "openapi-export")
os.environ.setdefault("WHATSAPP_NUMBER", "0000000000")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402

DEFAULT_OUTPUT_PATH = BACKEND_DIR / "openapi.json"


def main(output_path: Path = DEFAULT_OUTPUT_PATH) -> None:
    schema = app.openapi()
    output_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"Wrote OpenAPI schema to {output_path}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_PATH
    main(target)
