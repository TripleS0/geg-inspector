"""Authentication and admin user management tests."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from app.application.auth_use_cases import AuthUseCase, DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME
from app.application.bootstrap import bootstrap_database
from app.services.shared.db.sqlite_client import SqliteClient


class AuthUseCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_db = os.environ.get("DATAFUSIONX_DB_PATH")
        os.environ["DATAFUSIONX_DB_PATH"] = str(Path(self._tmp.name) / "auth.sqlite3")
        from app import runtime_paths as rp

        importlib.reload(rp)
        self.client = SqliteClient()
        bootstrap_database(self.client)
        self.uc = AuthUseCase(self.client)
        self.uc.ensure_default_admin()

    def tearDown(self) -> None:
        if self._old_db is None:
            os.environ.pop("DATAFUSIONX_DB_PATH", None)
        else:
            os.environ["DATAFUSIONX_DB_PATH"] = self._old_db
        from app import runtime_paths as rp

        importlib.reload(rp)

    def test_schema_has_app_user(self) -> None:
        rows = self.client.query_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='app_user';"
        )
        self.assertEqual(len(rows), 1)
        versions = [row[0] for row in self.client.query_all("SELECT version FROM meta_schema_version;")]
        self.assertIn(6, versions)

    def test_default_admin_login(self) -> None:
        token, user = self.uc.login(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)
        self.assertTrue(token)
        self.assertEqual(user.username, "admin")
        self.assertEqual(user.role, "admin")
        decoded = self.uc.decode_token(token)
        self.assertEqual(decoded.user_id, user.user_id)

    def test_bad_password(self) -> None:
        with self.assertRaises(ValueError):
            self.uc.login("admin", "wrong-password")

    def test_create_update_delete_user(self) -> None:
        admin = self.uc.get_user_by_username("admin")
        assert admin is not None
        user = self.uc.create_user(username="alice", password="alice12", display_name="Alice", role="user")
        self.assertEqual(user.username, "alice")
        self.assertEqual(user.role, "user")

        updated = self.uc.update_user(
            user.user_id,
            actor=admin,
            display_name="Alice Wang",
            is_active=False,
        )
        self.assertEqual(updated.display_name, "Alice Wang")
        self.assertFalse(updated.is_active)

        with self.assertRaises(ValueError):
            self.uc.login("alice", "alice12")

        self.uc.update_user(user.user_id, actor=admin, is_active=True, password="alice99")
        token, logged = self.uc.login("alice", "alice99")
        self.assertEqual(logged.username, "alice")
        self.assertTrue(token)

        self.uc.delete_user(user.user_id, actor=admin)
        self.assertIsNone(self.uc.get_user(user.user_id))

    def test_cannot_disable_self_or_last_admin(self) -> None:
        admin = self.uc.get_user_by_username("admin")
        assert admin is not None
        with self.assertRaises(ValueError):
            self.uc.update_user(admin.user_id, actor=admin, is_active=False)
        with self.assertRaises(ValueError):
            self.uc.delete_user(admin.user_id, actor=admin)


class AuthApiTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from fastapi.testclient import TestClient  # noqa: F401
        except Exception as err:  # pragma: no cover
            self.skipTest(f"fastapi/starlette not installed: {err}")

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_db = os.environ.get("DATAFUSIONX_DB_PATH")
        self._old_home = os.environ.get("DATAFUSIONX_HOME")
        os.environ["DATAFUSIONX_DB_PATH"] = str(Path(self._tmp.name) / "auth_api.sqlite3")
        os.environ["DATAFUSIONX_HOME"] = self._tmp.name

        from app import runtime_paths as rp

        importlib.reload(rp)
        from backend import main as backend_main

        importlib.reload(backend_main)
        from fastapi.testclient import TestClient

        self.app_module = backend_main
        self.client = TestClient(backend_main.app)

    def tearDown(self) -> None:
        if self._old_db is None:
            os.environ.pop("DATAFUSIONX_DB_PATH", None)
        else:
            os.environ["DATAFUSIONX_DB_PATH"] = self._old_db
        if self._old_home is None:
            os.environ.pop("DATAFUSIONX_HOME", None)
        else:
            os.environ["DATAFUSIONX_HOME"] = self._old_home
        from app import runtime_paths as rp

        importlib.reload(rp)
        from backend import main as backend_main

        importlib.reload(backend_main)

    def _login(self, username: str = "admin", password: str = "admin123") -> dict:
        resp = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def _auth_headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_login_and_me(self) -> None:
        body = self._login()
        self.assertIn("access_token", body)
        self.assertEqual(body["user"]["role"], "admin")
        me = self.client.get("/api/auth/me", headers=self._auth_headers(body["access_token"]))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["username"], "admin")

    def test_protected_route_requires_auth(self) -> None:
        resp = self.client.get("/api/batches")
        self.assertEqual(resp.status_code, 401)

    def test_user_cannot_manage_users(self) -> None:
        admin = self._login()
        create = self.client.post(
            "/api/users",
            headers=self._auth_headers(admin["access_token"]),
            json={"username": "bob", "password": "bob1234", "role": "user"},
        )
        self.assertEqual(create.status_code, 200, create.text)

        bob = self._login("bob", "bob1234")
        denied = self.client.get("/api/users", headers=self._auth_headers(bob["access_token"]))
        self.assertEqual(denied.status_code, 403)

        ok = self.client.get("/api/batches", headers=self._auth_headers(bob["access_token"]))
        self.assertEqual(ok.status_code, 200)

    def test_admin_user_crud(self) -> None:
        admin = self._login()
        headers = self._auth_headers(admin["access_token"])
        create = self.client.post(
            "/api/users",
            headers=headers,
            json={"username": "carol", "password": "carol12", "display_name": "Carol", "role": "user"},
        )
        self.assertEqual(create.status_code, 200, create.text)
        user_id = create.json()["user_id"]

        patch = self.client.patch(
            f"/api/users/{user_id}",
            headers=headers,
            json={"is_active": False, "display_name": "Carol X"},
        )
        self.assertEqual(patch.status_code, 200, patch.text)
        self.assertFalse(patch.json()["is_active"])

        deleted = self.client.delete(f"/api/users/{user_id}", headers=headers)
        self.assertEqual(deleted.status_code, 200, deleted.text)


if __name__ == "__main__":
    unittest.main()
