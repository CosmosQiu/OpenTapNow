#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database manager for Tapnow production features.
MySQL is the primary backend (via SQLAlchemy + PyMySQL).
"""

import os
import json
import time
import uuid
import hmac
import base64
import hashlib
import secrets
from contextlib import contextmanager
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    create_engine, MetaData, Table, Column,
    String, Text, Integer, BigInteger, LargeBinary, func, text,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import select, and_


def _now_ts() -> int:
    return int(time.time())


def _new_id() -> str:
    return str(uuid.uuid4())


def _hash_password(password: str, salt_b64: str) -> str:
    salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 180_000)
    return base64.urlsafe_b64encode(dk).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    return f"pbkdf2_sha256${salt_b64}${_hash_password(password, salt_b64)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, salt_b64, expected = password_hash.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        actual = _hash_password(password, salt_b64)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class DatabaseManager:
    def __init__(self):
        self.database_url = (
            os.environ.get("TAPNOW_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or ""
        ).strip()
        self.enabled = bool(self.database_url)
        self.engine = None
        self.metadata = MetaData()
        self._init_tables()

    def _init_tables(self):
        asset_blob_type = LargeBinary().with_variant(LONGBLOB(), "mysql")

        self.users = Table(
            "users",
            self.metadata,
            Column("id", String(36), primary_key=True),
            Column("username", String(128), nullable=False, unique=True),
            Column("password_hash", String(255), nullable=False),
            Column("display_name", String(128), nullable=False, default=""),
            Column("is_active", Integer, nullable=False, default=1),
            Column("created_at", BigInteger, nullable=False),
            Column("updated_at", BigInteger, nullable=False),
        )

        self.sessions = Table(
            "sessions",
            self.metadata,
            Column("id", String(36), primary_key=True),
            Column("user_id", String(36), ForeignKey("users.id"), nullable=False),
            Column("token_hash", String(64), nullable=False, unique=True),
            Column("expires_at", BigInteger, nullable=False),
            Column("created_at", BigInteger, nullable=False),
            Column("revoked_at", BigInteger, nullable=True),
        )

        self.projects = Table(
            "projects",
            self.metadata,
            Column("id", String(36), primary_key=True),
            Column("slug", String(128), nullable=False, unique=True),
            Column("name", String(255), nullable=False),
            Column("current_state_json", Text, nullable=False, default="{}"),
            Column("state_version", BigInteger, nullable=False, default=0),
            Column("updated_by", String(36), nullable=True),
            Column("updated_at", BigInteger, nullable=False),
            Column("created_at", BigInteger, nullable=False),
        )

        self.assets = Table(
            "assets",
            self.metadata,
            Column("id", String(36), primary_key=True),
            Column("project_id", String(36), ForeignKey("projects.id"), nullable=False),
            Column("asset_type", String(32), nullable=False),
            Column("mime_type", String(255), nullable=False),
            Column("filename", String(512), nullable=False),
            Column("ext", String(32), nullable=False, default=""),
            Column("byte_size", BigInteger, nullable=False),
            Column("content_blob", asset_blob_type, nullable=False),
            Column("meta_json", Text, nullable=False, default="{}"),
            Column("created_by", String(36), nullable=True),
            Column("created_at", BigInteger, nullable=False),
            Column("deleted_at", BigInteger, nullable=True),
            Column("deleted_by", String(36), nullable=True),
        )

        self.system_configs = Table(
            "system_configs",
            self.metadata,
            Column("id", String(36), primary_key=True),
            Column("config_key", String(128), nullable=False, unique=True),
            Column("config_value_json", Text, nullable=False),
            Column("updated_by", String(36), nullable=True),
            Column("updated_at", BigInteger, nullable=False),
        )

        self.workflows = Table(
            "workflows",
            self.metadata,
            Column("id", String(36), primary_key=True),
            Column("project_id", String(36), ForeignKey("projects.id"), nullable=False),
            Column("name", String(255), nullable=False),
            Column("latest_version_no", Integer, nullable=False, default=0),
            Column("created_by", String(36), nullable=True),
            Column("created_at", BigInteger, nullable=False),
            Column("updated_at", BigInteger, nullable=False),
            UniqueConstraint("project_id", "name", name="uq_workflow_project_name"),
        )

        self.workflow_versions = Table(
            "workflow_versions",
            self.metadata,
            Column("id", String(36), primary_key=True),
            Column("workflow_id", String(36), ForeignKey("workflows.id"), nullable=False),
            Column("version_no", Integer, nullable=False),
            Column("content_json", Text, nullable=False),
            Column("save_type", String(32), nullable=False, default="manual"),
            Column("comment", Text, nullable=True),
            Column("saved_at", BigInteger, nullable=False),
            Column("saved_by", String(36), nullable=True),
            UniqueConstraint("workflow_id", "version_no", name="uq_workflow_version"),
        )

        self.audit_logs = Table(
            "audit_logs",
            self.metadata,
            Column("id", String(36), primary_key=True),
            Column("actor_user_id", String(36), nullable=True),
            Column("project_id", String(36), nullable=True),
            Column("action", String(64), nullable=False),
            Column("target_type", String(64), nullable=False),
            Column("target_id", String(128), nullable=True),
            Column("payload_json", Text, nullable=False, default="{}"),
            Column("created_at", BigInteger, nullable=False),
        )

    def init(self):
        if not self.enabled:
            return
        connect_args = {}
        if self.database_url.startswith("mysql"):
            connect_args = {"charset": "utf8mb4"}
        self.engine = create_engine(self.database_url, pool_pre_ping=True, future=True, connect_args=connect_args)
        self.metadata.create_all(self.engine)
        self._ensure_mysql_asset_blob_capacity()
        print("[数据库] 表结构初始化完成")
        self._ensure_default_project()
        self._ensure_default_admin()
        # 统计表数据
        with self.connection() as conn:
            user_count = conn.execute(select(func.count()).select_from(self.users)).scalar() or 0
            project_count = conn.execute(select(func.count()).select_from(self.projects)).scalar() or 0
            workflow_count = conn.execute(select(func.count()).select_from(self.workflows)).scalar() or 0
            asset_count = conn.execute(select(func.count()).select_from(self.assets)).scalar() or 0
        print(f"[数据库] 初始化完成: 用户={user_count}, 项目={project_count}, 工作流={workflow_count}, 资源={asset_count}")
        # 输出默认管理员信息
        admin_user = os.environ.get("TAPNOW_DEFAULT_ADMIN_USER", "admin")
        print(f"[数据库] 默认管理员账号: {admin_user} / {os.environ.get('TAPNOW_DEFAULT_ADMIN_PASSWORD', 'admin123')}")

    def _ensure_mysql_asset_blob_capacity(self):
        if not self.database_url.startswith("mysql") or not self.engine:
            return
        try:
            with self.engine.begin() as conn:
                row = conn.execute(text(
                    """
                    SELECT DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'assets'
                      AND COLUMN_NAME = 'content_blob'
                    """
                )).first()
                data_type = ((row[0] if row else "") or "").lower()
                if data_type and data_type != "longblob":
                    conn.execute(text("ALTER TABLE assets MODIFY COLUMN content_blob LONGBLOB NOT NULL"))
                    print("[数据库] 已将 assets.content_blob 升级为 LONGBLOB")
        except Exception as e:
            print(f"[数据库] 升级 assets.content_blob 失败: {e}")

    @contextmanager
    def connection(self):
        if not self.enabled or not self.engine:
            raise RuntimeError("Database not enabled")
        with self.engine.begin() as conn:
            yield conn

    def _ensure_default_project(self):
        now = _now_ts()
        with self.connection() as conn:
            row = conn.execute(select(self.projects.c.id).where(self.projects.c.slug == "default-project")).first()
            if row:
                return
            conn.execute(self.projects.insert().values(
                id=_new_id(),
                slug="default-project",
                name="Default Project",
                current_state_json="{}",
                state_version=0,
                updated_by=None,
                updated_at=now,
                created_at=now,
            ))

    def _ensure_default_admin(self):
        username = os.environ.get("TAPNOW_DEFAULT_ADMIN_USER", "admin")
        password = os.environ.get("TAPNOW_DEFAULT_ADMIN_PASSWORD", "admin123")
        now = _now_ts()
        with self.connection() as conn:
            row = conn.execute(select(self.users.c.id).where(self.users.c.username == username)).first()
            if row:
                return
            conn.execute(self.users.insert().values(
                id=_new_id(),
                username=username,
                password_hash=hash_password(password),
                display_name="Administrator",
                is_active=1,
                created_at=now,
                updated_at=now,
            ))

    def is_admin_user(self, user: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(user, dict):
            return False
        admin_username = os.environ.get("TAPNOW_DEFAULT_ADMIN_USER", "admin")
        return (user.get("username") or "") == admin_username

    def get_default_project_id(self) -> Optional[str]:
        if not self.enabled:
            return None
        with self.connection() as conn:
            row = conn.execute(select(self.projects.c.id).where(self.projects.c.slug == "default-project")).first()
            return row[0] if row else None

    def create_user(self, username: str, password: str, display_name: str = "") -> Dict[str, Any]:
        now = _now_ts()
        user_id = _new_id()
        with self.connection() as conn:
            conn.execute(self.users.insert().values(
                id=user_id,
                username=username,
                password_hash=hash_password(password),
                display_name=display_name or username,
                is_active=1,
                created_at=now,
                updated_at=now,
            ))
        return {"id": user_id, "username": username, "display_name": display_name or username}

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        with self.connection() as conn:
            row = conn.execute(select(self.users).where(self.users.c.username == username)).mappings().first()
            if not row or int(row.get("is_active") or 0) != 1:
                return None
            if not verify_password(password, row.get("password_hash") or ""):
                return None
            raw_token = secrets.token_urlsafe(36)
            expires_at = _now_ts() + 7 * 24 * 3600
            conn.execute(self.sessions.insert().values(
                id=_new_id(),
                user_id=row["id"],
                token_hash=hash_token(raw_token),
                expires_at=expires_at,
                created_at=_now_ts(),
                revoked_at=None,
            ))
            return {
                "token": raw_token,
                "expires_at": expires_at,
                "user": {
                    "id": row["id"],
                    "username": row["username"],
                    "display_name": row.get("display_name") or row["username"],
                    "is_admin": (row.get("username") or "") == os.environ.get("TAPNOW_DEFAULT_ADMIN_USER", "admin"),
                }
            }

    def resolve_user_by_token(self, raw_token: str) -> Optional[Dict[str, Any]]:
        if not self.enabled or not raw_token:
            return None
        token_h = hash_token(raw_token)
        now = _now_ts()
        with self.connection() as conn:
            session_row = conn.execute(
                select(self.sessions).where(and_(
                    self.sessions.c.token_hash == token_h,
                    self.sessions.c.revoked_at.is_(None),
                    self.sessions.c.expires_at > now,
                ))
            ).mappings().first()
            if not session_row:
                return None
            user_row = conn.execute(select(self.users).where(self.users.c.id == session_row["user_id"]))
            user_row = user_row.mappings().first()
            if not user_row:
                return None
            return {
                "id": user_row["id"],
                "username": user_row["username"],
                "display_name": user_row.get("display_name") or user_row["username"],
                "is_admin": (user_row.get("username") or "") == os.environ.get("TAPNOW_DEFAULT_ADMIN_USER", "admin"),
            }

    def list_users_for_admin(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                select(self.users).order_by(self.users.c.created_at.asc())
            ).mappings().all()
            admin_username = os.environ.get("TAPNOW_DEFAULT_ADMIN_USER", "admin")
            return [{
                "id": row["id"],
                "username": row["username"],
                "display_name": row.get("display_name") or row["username"],
                "is_active": int(row.get("is_active") or 0) == 1,
                "is_admin": (row.get("username") or "") == admin_username,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            } for row in rows]

    def create_user_for_admin(self, username: str, password: str, display_name: str = "") -> Dict[str, Any]:
        username = (username or "").strip()
        if not username:
            raise ValueError("用户名不能为空")
        if not password:
            raise ValueError("密码不能为空")

        now = _now_ts()
        user_id = _new_id()
        with self.connection() as conn:
            existing = conn.execute(
                select(self.users.c.id).where(self.users.c.username == username)
            ).first()
            if existing:
                raise ValueError("用户名已存在")
            conn.execute(self.users.insert().values(
                id=user_id,
                username=username,
                password_hash=hash_password(password),
                display_name=(display_name or username),
                is_active=1,
                created_at=now,
                updated_at=now,
            ))

        return {
            "id": user_id,
            "username": username,
            "display_name": display_name or username,
            "is_active": True,
            "is_admin": username == os.environ.get("TAPNOW_DEFAULT_ADMIN_USER", "admin"),
            "created_at": now,
            "updated_at": now,
        }

    def update_user_password_for_admin(self, user_id: str, new_password: str) -> bool:
        if not new_password:
            raise ValueError("新密码不能为空")
        now = _now_ts()
        with self.connection() as conn:
            result = conn.execute(
                self.users.update()
                .where(self.users.c.id == user_id)
                .values(password_hash=hash_password(new_password), updated_at=now)
            )
            return (result.rowcount or 0) > 0

    def delete_user_for_admin(self, user_id: str) -> bool:
        with self.connection() as conn:
            result = conn.execute(self.users.delete().where(self.users.c.id == user_id))
            return (result.rowcount or 0) > 0

    def revoke_token(self, raw_token: str):
        if not self.enabled or not raw_token:
            return
        with self.connection() as conn:
            conn.execute(
                self.sessions.update().where(self.sessions.c.token_hash == hash_token(raw_token)).values(revoked_at=_now_ts())
            )

    def save_asset(
        self,
        *,
        asset_type: str,
        filename: str,
        mime_type: str,
        content: bytes,
        created_by: Optional[str],
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        project_id = self.get_default_project_id()
        if not project_id:
            # 默认项目可能被误删，自动补建以确保资源可持久化
            self._ensure_default_project()
            project_id = self.get_default_project_id()
        if not project_id:
            with self.connection() as conn:
                row = conn.execute(
                    select(self.projects.c.id).order_by(self.projects.c.created_at.asc())
                ).first()
                project_id = row[0] if row else None
        if not project_id:
            raise RuntimeError("无法保存资源：没有可用项目")

        now = _now_ts()
        asset_id = _new_id()
        ext = os.path.splitext(filename or "")[1].lower()
        with self.connection() as conn:
            conn.execute(self.assets.insert().values(
                id=asset_id,
                project_id=project_id,
                asset_type=asset_type,
                mime_type=mime_type or "application/octet-stream",
                filename=filename or f"asset-{asset_id}",
                ext=ext,
                byte_size=len(content),
                content_blob=content,
                meta_json=json.dumps(meta or {}, ensure_ascii=False),
                created_by=created_by,
                created_at=now,
                deleted_at=None,
                deleted_by=None,
            ))
        return {
            "id": asset_id,
            "filename": filename,
            "size": len(content),
            "mime_type": mime_type,
            "created_at": now,
            "rel_path": f"db/{asset_id}/{filename or 'asset.bin'}",
            "url": f"/file/db/{asset_id}/{filename or 'asset.bin'}",
        }

    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                select(self.assets).where(and_(self.assets.c.id == asset_id, self.assets.c.deleted_at.is_(None)))
            ).mappings().first()
            return dict(row) if row else None

    def list_assets(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                select(self.assets).where(self.assets.c.deleted_at.is_(None)).order_by(self.assets.c.created_at.desc())
            ).mappings().all()
            return [dict(r) for r in rows]

    def delete_asset(self, asset_id: str, user_id: Optional[str]) -> bool:
        with self.connection() as conn:
            result = conn.execute(
                self.assets.update()
                .where(and_(self.assets.c.id == asset_id, self.assets.c.deleted_at.is_(None)))
                .values(deleted_at=_now_ts(), deleted_by=user_id)
            )
            return (result.rowcount or 0) > 0

    def upsert_config(self, key: str, value: Dict[str, Any], user_id: Optional[str]):
        now = _now_ts()
        payload = json.dumps(value or {}, ensure_ascii=False)
        with self.connection() as conn:
            row = conn.execute(select(self.system_configs.c.id).where(self.system_configs.c.config_key == key)).first()
            if row:
                conn.execute(
                    self.system_configs.update()
                    .where(self.system_configs.c.id == row[0])
                    .values(config_value_json=payload, updated_by=user_id, updated_at=now)
                )
            else:
                conn.execute(self.system_configs.insert().values(
                    id=_new_id(),
                    config_key=key,
                    config_value_json=payload,
                    updated_by=user_id,
                    updated_at=now,
                ))

    def get_config(self, key: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(select(self.system_configs).where(self.system_configs.c.config_key == key)).mappings().first()
            if not row:
                return None
            try:
                return json.loads(row["config_value_json"])
            except Exception:
                return None

    def save_workflow_version(
        self,
        *,
        name: str,
        content: Dict[str, Any],
        saved_by: Optional[str],
        save_type: str = "manual",
        comment: str = "",
    ) -> Dict[str, Any]:
        now = _now_ts()
        project_id = self.get_default_project_id()
        with self.connection() as conn:
            wf_row = conn.execute(
                select(self.workflows).where(and_(self.workflows.c.project_id == project_id, self.workflows.c.name == name))
            ).mappings().first()
            if not wf_row:
                workflow_id = _new_id()
                conn.execute(self.workflows.insert().values(
                    id=workflow_id,
                    project_id=project_id,
                    name=name,
                    latest_version_no=0,
                    created_by=saved_by,
                    created_at=now,
                    updated_at=now,
                ))
                version_no = 1
            else:
                workflow_id = wf_row["id"]
                version_no = int(wf_row.get("latest_version_no") or 0) + 1

            conn.execute(self.workflow_versions.insert().values(
                id=_new_id(),
                workflow_id=workflow_id,
                version_no=version_no,
                content_json=json.dumps(content or {}, ensure_ascii=False),
                save_type=save_type,
                comment=comment or "",
                saved_at=now,
                saved_by=saved_by,
            ))
            conn.execute(
                self.workflows.update()
                .where(self.workflows.c.id == workflow_id)
                .values(latest_version_no=version_no, updated_at=now)
            )
        return {
            "workflow_id": workflow_id,
            "name": name,
            "version_no": version_no,
            "saved_at": now,
        }

    def get_latest_workflow_content(self, name: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            wf_row = conn.execute(select(self.workflows).where(self.workflows.c.name == name)).mappings().first()
            if not wf_row:
                return None
            ver_row = conn.execute(
                select(self.workflow_versions)
                .where(and_(
                    self.workflow_versions.c.workflow_id == wf_row["id"],
                    self.workflow_versions.c.version_no == wf_row["latest_version_no"],
                ))
            ).mappings().first()
            if not ver_row:
                return None
            try:
                return json.loads(ver_row["content_json"])
            except Exception:
                return None

    def list_workflows(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(select(self.workflows).order_by(self.workflows.c.updated_at.desc())).mappings().all()
            return [dict(r) for r in rows]

    def list_workflow_versions(self, workflow_name: str) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            wf_row = conn.execute(select(self.workflows).where(self.workflows.c.name == workflow_name)).mappings().first()
            if not wf_row:
                return []
            rows = conn.execute(
                select(self.workflow_versions)
                .where(self.workflow_versions.c.workflow_id == wf_row["id"])
                .order_by(self.workflow_versions.c.version_no.desc())
            ).mappings().all()
            return [dict(r) for r in rows]

    def write_audit(self, *, actor_user_id: Optional[str], action: str, target_type: str, target_id: str = "", payload: Optional[Dict[str, Any]] = None):
        if not self.enabled:
            return
        with self.connection() as conn:
            conn.execute(self.audit_logs.insert().values(
                id=_new_id(),
                actor_user_id=actor_user_id,
                project_id=self.get_default_project_id(),
                action=action,
                target_type=target_type,
                target_id=target_id or None,
                payload_json=json.dumps(payload or {}, ensure_ascii=False),
                created_at=_now_ts(),
            ))


db_manager = DatabaseManager()
