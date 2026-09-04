from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

from app.core.config import settings

def _connect_args(url: str) -> dict:
    #Argumentos especificos para SQLite

    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args(settings.DATABASE_URL),
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db() -> Iterator[Session]:
    """ Dependencia de FastAPI: Una sesion por request (peticion) de la base de datos
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        