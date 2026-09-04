from tests.conftest import TEST_PASSWORD


def _payload(**overrides):
    base = {
        "name": "Nuevo Usuario",
        "email": "nuevo@empresa.com",
        "password": "NuevaClave123",
        "role": "EMPLOYEE",
        "shift": "SHIFT_3",
    }
    base.update(overrides)
    return base


class TestPermissions:
    def test_requires_auth(self, client, users):
        assert client.get("/api/v1/users").status_code == 401

    def test_employee_forbidden(self, client, users, login_as):
        headers = login_as("t1@empresa.com")
        assert client.get("/api/v1/users", headers=headers).status_code == 403
        assert client.post("/api/v1/users", json=_payload(), headers=headers).status_code == 403
        assert client.patch("/api/v1/users/1", json={"name": "x"}, headers=headers).status_code == 403
        assert client.delete("/api/v1/users/1", headers=headers).status_code == 403

    def test_supervisor_forbidden(self, client, users, login_as):
        headers = login_as("supervisor@empresa.com")
        assert client.get("/api/v1/users", headers=headers).status_code == 403

    def test_admin_allowed(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        assert client.get("/api/v1/users", headers=headers).status_code == 200


class TestCreate:
    def test_create_employee(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        response = client.post(
            "/api/v1/users", json=_payload(rotation_position=7, is_active=True), headers=headers
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "nuevo@empresa.com"
        assert body["rotation_position"] == 7
        assert "password" not in body and "password_hash" not in body
        # El usuario creado puede iniciar sesión (hash correcto, nunca texto plano).
        login = client.post(
            "/api/v1/auth/login", json={"email": "nuevo@empresa.com", "password": "NuevaClave123"}
        )
        assert login.status_code == 200

    def test_email_is_normalized(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        response = client.post("/api/v1/users", json=_payload(email="  Otro@Empresa.COM "), headers=headers)
        assert response.status_code == 201
        assert response.json()["email"] == "otro@empresa.com"

    def test_duplicate_email_conflict(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        response = client.post("/api/v1/users", json=_payload(email="t1@empresa.com"), headers=headers)
        assert response.status_code == 409

    def test_invalid_role_or_shift(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        assert client.post("/api/v1/users", json=_payload(role="OWNER"), headers=headers).status_code == 422
        assert client.post("/api/v1/users", json=_payload(shift="HOLIDAY"), headers=headers).status_code == 422

    def test_short_password_rejected(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        assert client.post("/api/v1/users", json=_payload(password="corta"), headers=headers).status_code == 422

    def test_created_employee_enters_rotation(self, client, db, users, login_as):
        from app.services import rotation_service

        headers = login_as("admin@empresa.com")
        response = client.post("/api/v1/users", json=_payload(rotation_position=99), headers=headers)
        assert response.status_code == 201
        rotating_ids = {u.id for u in rotation_service.get_rotating_employees(db)}
        assert response.json()["id"] in rotating_ids


class TestList:
    def test_list_all(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        assert len(client.get("/api/v1/users", headers=headers).json()) == len(users)

    def test_filter_role(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        body = client.get("/api/v1/users?role=EMPLOYEE", headers=headers).json()
        assert len(body) == 6  # 5 empleados activos + 1 inactivo
        assert all(user["role"] == "EMPLOYEE" for user in body)

    def test_filter_active(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        body = client.get("/api/v1/users?active=false", headers=headers).json()
        assert [user["email"] for user in body] == ["inactivo@empresa.com"]


class TestUpdate:
    def test_rename(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        user_id = users["t1@empresa.com"].id
        response = client.patch(f"/api/v1/users/{user_id}", json={"name": "Ana Renombrada"}, headers=headers)
        assert response.status_code == 200
        assert response.json()["name"] == "Ana Renombrada"

    def test_partial_update_keeps_other_fields(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        user_id = users["t2@empresa.com"].id
        body = client.patch(f"/api/v1/users/{user_id}", json={"rotation_position": 10}, headers=headers).json()
        assert body["rotation_position"] == 10
        assert body["shift"] == "SHIFT_2"  # lo no enviado no cambia (exclude_unset)

    def test_change_role_clears_position(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        user_id = users["t3@empresa.com"].id
        body = client.patch(f"/api/v1/users/{user_id}", json={"role": "SUPERVISOR"}, headers=headers).json()
        assert body["role"] == "SUPERVISOR"
        assert body["rotation_position"] is None

    def test_email_conflict(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        user_id = users["t1@empresa.com"].id
        response = client.patch(f"/api/v1/users/{user_id}", json={"email": "t2@empresa.com"}, headers=headers)
        assert response.status_code == 409

    def test_password_reset(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        user_id = users["t4@empresa.com"].id
        assert (
            client.patch(f"/api/v1/users/{user_id}", json={"password": "ClaveNueva123"}, headers=headers).status_code
            == 200
        )
        assert (
            client.post("/api/v1/auth/login", json={"email": "t4@empresa.com", "password": TEST_PASSWORD}).status_code
            == 401
        )
        assert (
            client.post("/api/v1/auth/login", json={"email": "t4@empresa.com", "password": "ClaveNueva123"}).status_code
            == 200
        )

    def test_reactivate(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        user_id = users["inactivo@empresa.com"].id
        assert client.patch(f"/api/v1/users/{user_id}", json={"is_active": True}, headers=headers).status_code == 200
        assert (
            client.post("/api/v1/auth/login", json={"email": "inactivo@empresa.com", "password": TEST_PASSWORD}).status_code
            == 200
        )

    def test_self_deactivation_forbidden(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        admin_id = users["admin@empresa.com"].id
        assert client.patch(f"/api/v1/users/{admin_id}", json={"is_active": False}, headers=headers).status_code == 400

    def test_self_role_change_forbidden(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        admin_id = users["admin@empresa.com"].id
        assert client.patch(f"/api/v1/users/{admin_id}", json={"role": "EMPLOYEE"}, headers=headers).status_code == 400

    def test_unknown_user(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        assert client.patch("/api/v1/users/99999", json={"name": "x"}, headers=headers).status_code == 404


class TestDelete:
    def test_deactivate_soft_delete(self, client, db, users, login_as):
        from app.services import rotation_service

        headers = login_as("admin@empresa.com")
        user_id = users["t5@empresa.com"].id
        assert client.delete(f"/api/v1/users/{user_id}", headers=headers).status_code == 204
        # La cuenta queda desactivada (no eliminada): login → 403.
        assert (
            client.post("/api/v1/auth/login", json={"email": "t5@empresa.com", "password": TEST_PASSWORD}).status_code
            == 403
        )
        # Sale de la rotación.
        rotating_ids = {u.id for u in rotation_service.get_rotating_employees(db)}
        assert user_id not in rotating_ids

    def test_self_delete_forbidden(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        admin_id = users["admin@empresa.com"].id
        assert client.delete(f"/api/v1/users/{admin_id}", headers=headers).status_code == 400

    def test_unknown(self, client, users, login_as):
        headers = login_as("admin@empresa.com")
        assert client.delete("/api/v1/users/99999", headers=headers).status_code == 404