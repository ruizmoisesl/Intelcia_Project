from app.core.security import create_access_token
from .conftest import TEST_PASSWORD


class TestLogin:
    def test_login_returns_token_and_user(self, client, users):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "t1@empresa.com", "password": TEST_PASSWORD},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["user"] == {
            "id": users["t1@empresa.com"].id,
            "name": "Empleado Turno 1",
            "email": "t1@empresa.com",
            "role": "EMPLOYEE",
            "shift": "SHIFT_1",
        }

    def test_login_wrong_password(self, client, users):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "t1@empresa.com", "password": "incorrecta"},
        )
        assert response.status_code == 401

    def test_login_unknown_email(self, client, users):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "nadie@empresa.com", "password": TEST_PASSWORD},
        )
        assert response.status_code == 401

    def test_login_inactive_user_is_forbidden(self, client, users):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "inactivo@empresa.com", "password": TEST_PASSWORD},
        )
        assert response.status_code == 403

    def test_login_invalid_email_format(self, client):
        response = client.post(
            "/api/v1/auth/login", json={"email": "no-es-un-correo", "password": "x"}
        )
        assert response.status_code == 422


class TestMe:
    def test_me_with_valid_token(self, client, users, login_as):
        headers = login_as("t2@empresa.com")
        response = client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200
        assert response.json()["shift"] == "SHIFT_2"

    def test_me_without_token(self, client, users):
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_me_with_invalid_token(self, client, users):
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer token-invalido"})
        assert response.status_code == 401

    def test_me_with_token_of_missing_user(self, client, users):
        token = create_access_token(user_id=999999, role="EMPLOYEE")
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    def test_me_with_token_of_inactive_user(self, client, users):
        token = create_access_token(user_id=users["inactivo@empresa.com"].id, role="EMPLOYEE")
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401