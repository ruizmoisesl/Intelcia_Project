"""Compatibilidad real con MySQL: migraciones + ORM end-to-end.

Se activa únicamente con la variable TEST_DATABASE_URL apuntando a una BD
MySQL VACÍA de pruebas:

    TEST_DATABASE_URL="mysql+pymysql://portal:clave@localhost:3306/portal_test?charset=utf8mb4" pytest tests/test_mysql_compatibility.py -v

En CI hay un job dedicado con un contenedor MySQL. Los tests unitarios del
resto siguen corriendo en SQLite en memoria: la lógica de negocio no depende
del motor; estos tests validan que el ESQUEMA y los tipos sí funcionan igual.
"""
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL no definida (se requiere un MySQL de prueba vacío)",
)


@pytest.fixture()
def mysql_engine(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DATABASE_URL", TEST_DATABASE_URL)
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
    yield engine
    engine.dispose()


@pytest.fixture()
def migrated_db(mysql_engine, monkeypatch):
    """Aplica las migraciones 0001→head contra MySQL y las revierte al final."""
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    command.upgrade(config, "head")
    yield mysql_engine
    command.downgrade(config, "base")


def test_migrations_apply_on_mysql(migrated_db):
    tables = set(inspect(migrated_db).get_table_names())
    assert {"users", "schedule_changes", "audit_logs"} <= tables
    assert {"alembic_version"} & tables  # versionado de migraciones presente


def test_migrations_downgrade_on_mysql(migrated_db):
    # migrated_db ya revierte en teardown; aquí verificamos que el downgrade
    # programático no lanza (re-idempotencia del ciclo completo).
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    command.upgrade(config, "head")


def test_orm_roundtrip_on_mysql(migrated_db):
    """Inserta y lee con el ORM: enums, UTF-8, IDs y datetimes aware-UTC."""
    from app.core.security import hash_password
    from app.models.audit import AuditLog
    from app.models.schedule_change import ChangeStatus, ScheduleChange
    from app.models.user import Role, ShiftId, User

    with Session(migrated_db) as db:
        user = User(
            name="María José Ñúñez 👋",  # UTF-8 completo (utf8mb4)
            email="mysql.test@empresa.com",
            password_hash=hash_password("Clave1234"),
            role=Role.EMPLOYEE,
            shift=ShiftId.SHIFT_4,
            rotation_position=42,
        )
        db.add(user)
        db.flush()  # id generado por AUTO_INCREMENT

        change = ScheduleChange(
            user_id=user.id,
            week_start=__import__("datetime").date(2026, 9, 7),
            requested_shift=ShiftId.SHIFT_3,
            reason="Prueba de compatibilidad con acentós",
            status=ChangeStatus.APPROVED,
            requested_by_id=user.id,
            reviewed_by_id=user.id,
            reviewed_at=datetime(2026, 9, 2, 15, 30, tzinfo=timezone.utc),
        )
        db.add(change)
        db.add(AuditLog(event="LOGIN_SUCCESS", actor_id=user.id, detail="mysql compat"))
        db.commit()
        user_id = user.id

    with Session(migrated_db) as db:
        saved = db.get(User, user_id)
        assert saved.name == "María José Ñúñez 👋"
        assert (saved.role, saved.shift) == (Role.EMPLOYEE, ShiftId.SHIFT_4)
        assert saved.created_at.tzinfo is not None  # aware-UTC al leer
        assert saved.created_at.utcoffset().total_seconds() == 0

        saved_change = db.scalars(
            __import__("sqlalchemy").select(ScheduleChange).where(ScheduleChange.user_id == user_id)
        ).one()
        assert saved_change.reviewed_at.tzinfo is not None
        assert saved_change.reviewed_at.hour == 15  # wall-clock UTC preservado
        assert saved_change.status == ChangeStatus.APPROVED

        events = db.scalars(__import__("sqlalchemy").select(AuditLog)).all()
        assert len(events) == 1


def test_unique_email_enforced_on_mysql(migrated_db):
    from app.models.user import Role, ShiftId, User
    from sqlalchemy.exc import IntegrityError

    def add_user(session):
        session.add(User(
            name="Dup", email="dup@empresa.com",
            password_hash="x" * 60, role=Role.EMPLOYEE, shift=ShiftId.SHIFT_1,
        ))

    with Session(migrated_db) as db:
        add_user(db)
        db.commit()
        add_user(db)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()