import os

# Variables de entorno de test ANTES de importar la aplicación.
os.environ.setdefault("SECRET_KEY", "secret-key-para-tests-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.user import Role, ShiftId, User

TEST_PASSWORD = "Clave1234!"

# BD en memoria compartida (StaticPool) para TestClient + fixtures.
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def users(db):
    """Usuarios de prueba en distintos turnos y estados."""
    data = [
        User(name="Admin Test", email="admin@empresa.com",
             password_hash=hash_password(TEST_PASSWORD), role=Role.ADMIN, shift=ShiftId.SHIFT_1),
        User(name="Empleado Turno 1", email="t1@empresa.com",
             password_hash=hash_password(TEST_PASSWORD), role=Role.EMPLOYEE, shift=ShiftId.SHIFT_1),
        User(name="Empleado Turno 2", email="t2@empresa.com",
             password_hash=hash_password(TEST_PASSWORD), role=Role.EMPLOYEE, shift=ShiftId.SHIFT_2),
        User(name="Empleado Turno 3", email="t3@empresa.com",
             password_hash=hash_password(TEST_PASSWORD), role=Role.EMPLOYEE, shift=ShiftId.SHIFT_3),
        User(name="Empleado Turno 4", email="t4@empresa.com",
             password_hash=hash_password(TEST_PASSWORD), role=Role.EMPLOYEE, shift=ShiftId.SHIFT_4),
        User(name="Usuario Inactivo", email="inactivo@empresa.com",
             password_hash=hash_password(TEST_PASSWORD), role=Role.EMPLOYEE,
             shift=ShiftId.SHIFT_1, is_active=False),
    ]
    db.add_all(data)
    db.commit()
    return {user.email: user for user in data}


@pytest.fixture()
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def login_as(client):
    """Devuelve una función que inicia sesión y devuelve los headers Bearer."""
    def _login(email: str) -> dict[str, str]:
        response = client.post(
            "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"login falló para {email}"
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    return _login