"""Baseline current schema."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op


def _load_snapshot_metadata():
    snapshot_path = Path(__file__).resolve().parents[1] / "schema_snapshot.py"
    spec = importlib.util.spec_from_file_location("pb_alembic_schema_snapshot", snapshot_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load schema snapshot from {snapshot_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.metadata


revision = "20260321_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    _load_snapshot_metadata().create_all(bind=op.get_bind())


def downgrade() -> None:
    _load_snapshot_metadata().drop_all(bind=op.get_bind())
