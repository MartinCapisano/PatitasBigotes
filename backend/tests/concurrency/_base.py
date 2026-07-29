"""Base para tests de concurrencia contra un PostgreSQL real.

El resto de la suite corre sobre SQLite en memoria con `StaticPool` (una sola
conexión compartida), y ahí `with_for_update()` es un **no-op silencioso**: no
prueba nada de la concurrencia real del sistema. Estos tests, en cambio, abren
varias conexiones reales y dejan que los locks a nivel de fila de PostgreSQL
serialicen a los contendientes.

Estos tests **destruyen datos** (truncan todas las tablas en cada `setUp`), así que
JAMÁS deben apuntar a una base real. Por eso NO leen el `DATABASE_URL` genérico —que
en local suele resolver a la base de desarrollo vía `.env`— sino una variable
**dedicada** `CONCURRENCY_DATABASE_URL` que solo se define en el job de CI. Si no está,
o si no es un Postgres cuyo nombre de base contiene "test", el test se **saltea**. Así,
correr la suite en local nunca toca la base de desarrollo.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base

# Variable dedicada (no el DATABASE_URL de la app): que sea distinta es justamente el
# seguro contra truncar una base real. El CI la setea; el `.env` de desarrollo no.
CONCURRENCY_DATABASE_URL_ENV = "CONCURRENCY_DATABASE_URL"

# Un lock que nunca se libera colgaría el job entero. Con lock_timeout, el perdedor
# de una carrera mal diseñada falla en segundos con un error claro en vez de trabar
# el CI. Una espera sana (el ganador commitea en milisegundos) queda muy por debajo.
_LOCK_TIMEOUT_MS = 15_000


def _resolve_concurrency_database_url() -> str | None:
    """El DATABASE_URL para concurrencia, solo si es seguro truncarlo.

    Devuelve None (→ el test se saltea) salvo que la variable dedicada esté seteada,
    apunte a PostgreSQL y el nombre de la base contenga "test". El chequeo de "test" es
    un cinturón de seguridad extra para que un valor mal puesto no borre datos reales.
    """
    raw = os.environ.get(CONCURRENCY_DATABASE_URL_ENV, "").strip()
    if not raw or not raw.startswith("postgresql"):
        return None
    database_name = (make_url(raw).database or "").lower()
    if "test" not in database_name:
        return None
    return raw


class ConcurrencyTestBase(unittest.TestCase):
    engine: Any = None
    SessionLocal: Any = None

    @classmethod
    def setUpClass(cls) -> None:
        database_url = _resolve_concurrency_database_url()
        if database_url is None:
            raise unittest.SkipTest(
                f"los tests de concurrencia requieren {CONCURRENCY_DATABASE_URL_ENV} "
                "apuntando a un PostgreSQL de test (nombre de base con 'test')"
            )
        cls.engine = create_engine(
            database_url,
            connect_args={"options": f"-c lock_timeout={_LOCK_TIMEOUT_MS}"},
        )
        # Red de seguridad para correr local contra un Postgres vacío: en CI el
        # esquema ya lo dejó `alembic upgrade head`, y create_all solo agrega tablas
        # faltantes, así que no pisa lo migrado.
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(
            bind=cls.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.engine is not None:
            cls.engine.dispose()

    def setUp(self) -> None:
        self._truncate_all()

    def _truncate_all(self) -> None:
        table_names = ", ".join(
            f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables)
        )
        with self.engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))

    def run_gated(
        self,
        first: Callable[[Session], Any],
        second: Callable[[Session], Any],
        *,
        block_grace_seconds: float = 1.0,
    ) -> GatedOutcome:
        """Corre `first` reteniendo su transacción abierta y luego `second` en paralelo.

        Este es el punto del test: `first` corre en la sesión 1 y **no commitea**, así que
        se queda con los locks de fila que haya tomado (`with_for_update()`). Recién ahí
        arranca `second` en otro hilo/sesión.

        - Con el lock correcto: `second` se **bloquea** contra el lock que retiene `first`.
          Tras `block_grace_seconds` sigue vivo (``second_blocked=True``); recién cuando
          `first` commitea, `second` avanza y ve el estado ya persistido.
        - Sin el lock (regresión): `second` no se bloquea y, como `first` todavía no
          commiteó, bajo READ COMMITTED **no ve** su escritura → duplica (doble pago /
          sobreventa). El test lo detecta tanto por ``second_blocked=False`` como por el
          invariante de negocio que cada test asevera después.

        Devuelve el valor de `first`, si `second` quedó bloqueado en la ventana, y el
        resultado de `second` como ``("ok", valor)`` o ``("error", excepción)``.
        """
        session_first = self.SessionLocal()
        session_second = self.SessionLocal()
        second_result: dict[str, tuple[str, Any]] = {}

        def run_second() -> None:
            try:
                value = second(session_second)
                session_second.commit()
                second_result["outcome"] = ("ok", value)
            except Exception as exc:  # noqa: BLE001 - se captura para aseverar en el test
                session_second.rollback()
                second_result["outcome"] = ("error", exc)
            finally:
                session_second.close()

        thread_second = threading.Thread(target=run_second)
        try:
            first_value = first(session_first)  # toma los locks; NO commitea todavía

            thread_second.start()
            time.sleep(block_grace_seconds)
            second_blocked = thread_second.is_alive()

            session_first.commit()  # libera los locks → `second` puede avanzar
            thread_second.join(timeout=30)
            self.assertFalse(
                thread_second.is_alive(),
                "el segundo worker no terminó tras liberar el lock (posible deadlock)",
            )
        finally:
            session_first.close()

        return GatedOutcome(
            first_value=first_value,
            second_blocked=second_blocked,
            second_outcome=second_result["outcome"],
        )


@dataclass
class GatedOutcome:
    first_value: Any
    second_blocked: bool
    second_outcome: tuple[str, Any]
