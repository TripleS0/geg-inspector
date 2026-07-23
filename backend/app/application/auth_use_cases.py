"""Authentication and application user management."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from app.application.bootstrap import bootstrap_database
from app.services.shared.db.sqlite_client import SqliteClient

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7


def jwt_secret() -> str:
    return os.environ.get("DATAFUSIONX_JWT_SECRET") or os.environ.get(
        "GEG_INSPECTOR_JWT_SECRET", "datafusionx-local-dev-jwt-secret"
    )


@dataclass
class UserInfo:
    user_id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    created_at: str
    updated_at: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AuthUseCase:
    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)

    def ensure_default_admin(self) -> None:
        rows = self._client.query_all(
            "SELECT user_id FROM app_user WHERE username=? LIMIT 1;",
            (DEFAULT_ADMIN_USERNAME,),
        )
        if rows:
            return
        self._client.execute(
            """
            INSERT INTO app_user(username, password_hash, display_name, role, is_active, updated_at)
            VALUES (?, ?, ?, 'admin', 1, CURRENT_TIMESTAMP);
            """,
            (
                DEFAULT_ADMIN_USERNAME,
                self.hash_password(DEFAULT_ADMIN_PASSWORD),
                "系统管理员",
            ),
        )

    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        try:
            return pwd_context.verify(password, password_hash)
        except Exception:
            return False

    def _row_to_user(self, row: tuple[Any, ...]) -> UserInfo:
        return UserInfo(
            user_id=int(row[0]),
            username=str(row[1]),
            display_name=str(row[2] or ""),
            role=str(row[3] or "user"),
            is_active=bool(int(row[4] or 0)),
            created_at=str(row[5]),
            updated_at=str(row[6]),
        )

    def get_user(self, user_id: int) -> UserInfo | None:
        rows = self._client.query_all(
            """
            SELECT user_id, username, display_name, role, is_active, created_at, updated_at
            FROM app_user WHERE user_id=?;
            """,
            (user_id,),
        )
        if not rows:
            return None
        return self._row_to_user(rows[0])

    def get_user_by_username(self, username: str) -> UserInfo | None:
        rows = self._client.query_all(
            """
            SELECT user_id, username, display_name, role, is_active, created_at, updated_at
            FROM app_user WHERE username=?;
            """,
            (username.strip(),),
        )
        if not rows:
            return None
        return self._row_to_user(rows[0])

    def _password_hash_for(self, username: str) -> str | None:
        rows = self._client.query_all(
            "SELECT password_hash FROM app_user WHERE username=?;",
            (username.strip(),),
        )
        if not rows:
            return None
        return str(rows[0][0])

    def list_users(self) -> list[UserInfo]:
        rows = self._client.query_all(
            """
            SELECT user_id, username, display_name, role, is_active, created_at, updated_at
            FROM app_user
            ORDER BY role ASC, user_id ASC;
            """
        )
        return [self._row_to_user(row) for row in rows]

    def login(self, username: str, password: str) -> tuple[str, UserInfo]:
        name = (username or "").strip()
        if not name or not password:
            raise ValueError("用户名或密码不能为空")
        user = self.get_user_by_username(name)
        password_hash = self._password_hash_for(name)
        if user is None or password_hash is None or not self.verify_password(password, password_hash):
            raise ValueError("用户名或密码错误")
        if not user.is_active:
            raise ValueError("账号已禁用，请联系管理员")
        token = self.create_access_token(user)
        return token, user

    def create_access_token(self, user: UserInfo) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user.user_id),
            "username": user.username,
            "role": user.role,
            "iat": now,
            "exp": now + timedelta(hours=JWT_EXPIRE_HOURS),
        }
        return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)

    def decode_token(self, token: str) -> UserInfo:
        try:
            payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError as err:
            raise ValueError("登录已过期，请重新登录") from err
        except jwt.InvalidTokenError as err:
            raise ValueError("无效的登录凭证") from err
        user_id = int(payload.get("sub") or 0)
        user = self.get_user(user_id)
        if user is None:
            raise ValueError("用户不存在或已被删除")
        if not user.is_active:
            raise ValueError("账号已禁用，请联系管理员")
        return user

    def create_user(
        self,
        *,
        username: str,
        password: str,
        display_name: str = "",
        role: str = "user",
        is_active: bool = True,
    ) -> UserInfo:
        name = (username or "").strip()
        if not name:
            raise ValueError("用户名不能为空")
        if len(name) < 2:
            raise ValueError("用户名至少 2 个字符")
        if not password or len(password) < 6:
            raise ValueError("密码至少 6 个字符")
        role_clean = (role or "user").strip().lower()
        if role_clean not in ("admin", "user"):
            raise ValueError("角色只能是 admin 或 user")
        if self.get_user_by_username(name) is not None:
            raise ValueError("用户名已存在")
        self._client.execute(
            """
            INSERT INTO app_user(username, password_hash, display_name, role, is_active, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
            """,
            (
                name,
                self.hash_password(password),
                (display_name or "").strip() or name,
                role_clean,
                1 if is_active else 0,
            ),
        )
        user = self.get_user_by_username(name)
        assert user is not None
        return user

    def update_user(
        self,
        user_id: int,
        *,
        actor: UserInfo,
        display_name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        password: str | None = None,
    ) -> UserInfo:
        target = self.get_user(user_id)
        if target is None:
            raise ValueError("用户不存在")

        next_role = target.role
        if role is not None:
            role_clean = role.strip().lower()
            if role_clean not in ("admin", "user"):
                raise ValueError("角色只能是 admin 或 user")
            next_role = role_clean

        next_active = target.is_active if is_active is None else bool(is_active)

        if actor.user_id == user_id:
            if next_role != "admin":
                raise ValueError("不能取消自己的管理员角色")
            if not next_active:
                raise ValueError("不能禁用自己的账号")

        if target.role == "admin" and (next_role != "admin" or not next_active):
            if self._active_admin_count() <= 1:
                raise ValueError("至少保留一名启用的管理员")

        if password is not None and password != "":
            if len(password) < 6:
                raise ValueError("密码至少 6 个字符")
            self._client.execute(
                """
                UPDATE app_user
                SET password_hash=?, updated_at=CURRENT_TIMESTAMP
                WHERE user_id=?;
                """,
                (self.hash_password(password), user_id),
            )

        self._client.execute(
            """
            UPDATE app_user
            SET display_name=COALESCE(?, display_name),
                role=?,
                is_active=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE user_id=?;
            """,
            (
                None if display_name is None else display_name.strip(),
                next_role,
                1 if next_active else 0,
                user_id,
            ),
        )
        updated = self.get_user(user_id)
        assert updated is not None
        return updated

    def delete_user(self, user_id: int, *, actor: UserInfo) -> None:
        target = self.get_user(user_id)
        if target is None:
            raise ValueError("用户不存在")
        if actor.user_id == user_id:
            raise ValueError("不能删除自己的账号")
        if target.role == "admin" and self._active_admin_count() <= 1:
            raise ValueError("至少保留一名启用的管理员")
        self._client.execute("DELETE FROM app_user WHERE user_id=?;", (user_id,))

    def _active_admin_count(self) -> int:
        rows = self._client.query_all(
            "SELECT COUNT(*) FROM app_user WHERE role='admin' AND is_active=1;"
        )
        return int(rows[0][0] if rows else 0)
