from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.core.config import settings


class UTCDateTime(TypeDecorator):
    """DateTime SIEMPRE en UTC, portable entre SQLite/MySQL/Postgres.

    Problema que resuelve: MySQL no almacena timezone-aware datetimes.
    - Bind: convierte aware → UTC wall-clock naive (naive pasa tal cual).
    - Result: el naive leído se interpreta como UTC y se devuelve aware.
    La app maneja siempre datetimes aware-UTC, con cualquier motor.
    """
    impl = DateTime(timezone=True)  # DDL idéntico al que ya usábamos
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None or value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=timezone.utc)


def utcnow() -> datetime:
    """«Ahora» en UTC aware (para defaults de columnas datetime)."""
    return datetime.now(timezone.utc)


def _engine_kwargs(url: str) -> dict:
    """Argumentos específicos por motor: la persistencia no depende de uno.

    - SQLite: check_same_thread=False (FastAPI, múltiples hilos).
    - MySQL: pool_recycle=3600 (el servidor corta conexiones idle por
      wait_timeout; junto a pool_pre_ping evita 'MySQL server has gone away').
    """
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    if url.startswith("mysql"):
        return {"pool_recycle": 3600}
    return {}


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    **_engine_kwargs(settings.DATABASE_URL),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base declarativa única para todos los modelos."""


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()