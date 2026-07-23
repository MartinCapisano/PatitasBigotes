from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from source.db.config import get_database_url
from source.services.post_commit_actions_s import (
    clear_post_commit_actions,
    dispatch_post_commit_actions,
)

DATABASE_URL = get_database_url()

# Nada mantiene vivas las conexiones de este pool: el servicio free de Render
# duerme a los ~15 min sin trafico y Supabase free corta las conexiones ociosas
# por su cuenta. Sin esto, la primera request despues de un rato de silencio
# agarra del pool un socket ya muerto y falla con un error de conexion que el
# usuario ve como un 500, aunque la base este perfectamente sana.
#
# pool_pre_ping hace un SELECT 1 antes de entregar la conexion y la reemplaza si
# esta rota: convierte esa falla en una reconexion transparente, al costo de un
# round-trip por checkout.
#
# pool_recycle=300 (5 min) descarta proactivamente toda conexion mas vieja que
# eso. El numero sale de quedar comodamente por debajo del timeout de ocio mas
# corto que tenemos enfrente -- el sleep de Render a los ~15 min -- para que el
# pre_ping sea la red de seguridad y no el mecanismo habitual. Recycle solo no
# alcanza (una conexion puede morir dentro de la ventana) y pre_ping solo tampoco
# es ideal (dejaria sockets viejos rotando indefinidamente); van juntos.
POOL_RECYCLE_SECONDS = 300

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=POOL_RECYCLE_SECONDS,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_transactional() -> Generator[Session, None, None]:
    """Commitea al salir de la ruta y recien ahi despacha los efectos externos.

    Las rutas que usan `get_db` commitean a mano y llaman a
    `dispatch_post_commit_actions` ellas mismas (`orders_r.py:318`). Las que usan
    esta dependencia no tenian donde hacerlo, y por eso mandaban SMTP adentro de
    la transaccion: si el mail fallaba, el registro entero hacia rollback.

    Despachar aca no puede romper la respuesta HTTP -- el despachador ya envuelve
    cada accion en su propio try/except (`post_commit_actions_s.py:70`). Sin esa
    garantia, un SMTP caido tumbaria todas las rutas de auth, no solo las que
    mandan mail.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
        dispatch_post_commit_actions(db=db, source="transactional")
    except Exception:
        db.rollback()
        # La transaccion no existio: lo que sea que se haya encolado hablaba de
        # datos que no quedaron en la base.
        clear_post_commit_actions(db=db)
        raise
    finally:
        db.close()


@contextmanager
def read_session_scope(db: Session | None):
    owns_session = db is None
    session = db or SessionLocal()
    try:
        yield session, owns_session
    finally:
        if owns_session:
            session.close()


@contextmanager
def write_session_scope(db: Session):
    if db is None:
        raise RuntimeError("db session is required for mutating operations")
    yield db, False
