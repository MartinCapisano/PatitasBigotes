import logging
import secrets

from fastapi import APIRouter, Header, HTTPException, status

from source.db.config import get_maintenance_run_token
from source.services.maintenance_s import run_all_maintenance

router = APIRouter()
logger = logging.getLogger(__name__)


def _extract_bearer_token(authorization: str) -> str:
    value = str(authorization or "").strip()
    if value.lower().startswith("bearer "):
        return value[len("bearer ") :].strip()
    return value


@router.post("/internal/maintenance/run")
def run_maintenance(authorization: str = Header(default="")):
    try:
        expected_token = get_maintenance_run_token()
    except RuntimeError:
        # Token not configured on this environment: the endpoint is effectively
        # disabled rather than open.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="maintenance endpoint not configured",
        )

    provided_token = _extract_bearer_token(authorization)
    if not provided_token or not secrets.compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid maintenance token",
        )

    result = run_all_maintenance()
    logger.info("event=maintenance_endpoint_run status=%s", result.get("status"))
    return {"data": result}
