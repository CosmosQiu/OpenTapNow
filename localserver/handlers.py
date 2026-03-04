#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP 处理器模块 - 处理所有 HTTP 请求
"""

import os
import json
import base64
import mimetypes
import urllib.request
import http.client
import uuid
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from email.utils import formatdate

from config import config, FEATURES, PIL_AVAILABLE, DEFAULT_PROXY_TIMEOUT, LOCAL_FILE_CACHE_CONTROL, COMFY_URL
from utils import (
    log, ensure_dir, is_path_allowed, normalize_rel_path, safe_join, get_unique_filename,
    is_image_file, is_video_file, is_media_content_type, is_media_path,
    convert_png_to_jpg, parse_proxy_target, is_proxy_target_allowed,
    iter_proxy_response_chunks, PROXY_SKIP_REQUEST_HEADERS, PROXY_SKIP_RESPONSE_HEADERS,
    PROXY_MEDIA_CACHE_CONTROL
)
from comfy_middleware import (
    ComfyMiddleware, resolve_job_by_request_id, build_detail_response, build_outputs_response,
    JOB_QUEUE, JOB_STATUS, STATUS_LOCK, PROMPT_TO_JOB
)
from api_config import api_config_manager
from db import db_manager

# ==============================================================================
# HTTP 请求处理器
# ==============================================================================

class TapnowFullHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # 覆盖默认日志，使用统一的 log 函数
        if config.get("log_enabled", True) and FEATURES.get("log_console", True):
            try:
                log(f"HTTP: {format % args}")
            except Exception:
                log("HTTP: request received")

    # --- 基础 Helper ---

    def _send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, HEAD, PUT, DELETE')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Expose-Headers', 'Content-Length, ETag, Last-Modified, Cache-Control')

    def _send_json(self, data, status=200):
        try:
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self._send_cors()
            self.end_headers()
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _read_json_body(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except:
            return None

    def _extract_bearer_token(self):
        auth = self.headers.get('Authorization', '') or ''
        if not auth.startswith('Bearer '):
            return ''
        return auth[7:].strip()

    def _get_current_user(self):
        if not db_manager.enabled:
            return None
        token = self._extract_bearer_token()
        if not token:
            return None
        try:
            return db_manager.resolve_user_by_token(token)
        except Exception:
            return None

    def _require_user(self):
        user = self._get_current_user()
        if user:
            return user
        self._send_json({"success": False, "error": "Unauthorized"}, 401)
        return None

    def _require_admin(self):
        user = self._require_user()
        if not user:
            return None
        if not db_manager.is_admin_user(user):
            self._send_json({"success": False, "error": "Forbidden"}, 403)
            return None
        return user

    def _audit(self, user, action, target_type, target_id='', payload=None):
        try:
            db_manager.write_audit(
                actor_user_id=(user or {}).get('id') if isinstance(user, dict) else None,
                action=action,
                target_type=target_type,
                target_id=target_id,
                payload=payload or {}
            )
        except Exception:
            pass

    def _load_server_config(self):
        if not db_manager.enabled:
            return
        data = db_manager.get_config('server_config')
        if not isinstance(data, dict):
            return
        for key in (
            'save_path', 'image_save_path', 'video_save_path', 'auto_create_dir',
            'allow_overwrite', 'convert_png_to_jpg', 'jpg_quality',
            'proxy_allowed_hosts', 'proxy_timeout', 'log_enabled'
        ):
            if key in data:
                config[key] = data[key]

    # --- Router ---

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        self._load_server_config()

        # 1. ComfyUI 路由
        if (path.startswith('/comfy/')
            or path.startswith('/w/v1/webapp/task/openapi')
            or path.startswith('/task/openapi')) and FEATURES['comfy_middleware']:
            self.handle_comfy_get(path, parsed)
            return

        # 2. 原有功能路由
        if path in ('/proxy', '/proxy/'):
            self.handle_proxy(parsed)
            return

        if path == '/status' or path == '/ping':
            self._send_json({
                "status": "running",
                "version": "2.3.0",
                "features": FEATURES,
                "config": {
                    "save_path": config["save_path"],
                    "image_save_path": config["image_save_path"] or config["save_path"],
                    "video_save_path": config["video_save_path"] or config["save_path"],
                    "port": config["port"],
                    "pil_available": PIL_AVAILABLE,
                    "convert_png_to_jpg": config["convert_png_to_jpg"]
                }
            })
            return

        if path == '/workflows':
            if db_manager.enabled:
                self._send_json({"success": True, "items": db_manager.list_workflows()})
            else:
                self._send_json({"success": True, "items": []})
            return

        if path == '/workflow-versions':
            workflow_name = parse_qs(parsed.query or '').get('name', [''])[0]
            if not workflow_name:
                self._send_json({"success": False, "error": "missing workflow name"}, 400)
                return
            if db_manager.enabled:
                self._send_json({"success": True, "items": db_manager.list_workflow_versions(workflow_name)})
            else:
                self._send_json({"success": True, "items": []})
            return

        if path == '/auth/me':
            user = self._get_current_user()
            if not user:
                self._send_json({"success": False, "error": "Unauthorized"}, 401)
                return
            self._send_json({"success": True, "user": user})
            return

        if path == '/admin/users':
            if not db_manager.enabled:
                self._send_json({"success": False, "error": "Database not enabled"}, 503)
                return
            admin_user = self._require_admin()
            if not admin_user:
                return
            try:
                users = db_manager.list_users_for_admin()
                self._send_json({"success": True, "users": users})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == '/projects':
            if not db_manager.enabled:
                self._send_json({"success": True, "projects": []})
                return
            try:
                with db_manager.connection() as conn:
                    from sqlalchemy import select, or_
                    projects_table = db_manager.projects
                    users_table = db_manager.users
                    rows = conn.execute(
                        select(
                            projects_table,
                            users_table.c.display_name.label("updated_by_display_name"),
                            users_table.c.username.label("updated_by_username"),
                        )
                        .select_from(
                            projects_table.outerjoin(
                                users_table,
                                or_(
                                    projects_table.c.updated_by == users_table.c.id,
                                    projects_table.c.updated_by == users_table.c.username,
                                )
                            )
                        )
                        .order_by(projects_table.c.updated_at.desc())
                    ).mappings().all()
                    projects = []
                    for row in rows:
                        display_name = row.get("updated_by_display_name") or row.get("updated_by_username") or row.get("updated_by") or ''
                        projects.append({
                            "id": row["id"],
                            "slug": row["slug"],
                            "name": row["name"],
                            "state_version": row["state_version"],
                            "updated_by": row["updated_by"],
                            "updated_by_display_name": display_name,
                            "updated_at": row["updated_at"],
                            "created_at": row["created_at"],
                        })
                    self._send_json({"success": True, "projects": projects})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path.startswith('/projects/'):
            if not db_manager.enabled:
                self._send_json({"success": False, "error": "Database not enabled"}, 503)
                return
            try:
                project_id = path.split('/')[-1]
                with db_manager.connection() as conn:
                    from sqlalchemy import select, or_
                    projects_table = db_manager.projects
                    users_table = db_manager.users
                    row = conn.execute(
                        select(
                            projects_table,
                            users_table.c.display_name.label("updated_by_display_name"),
                            users_table.c.username.label("updated_by_username"),
                        )
                        .select_from(
                            projects_table.outerjoin(
                                users_table,
                                or_(
                                    projects_table.c.updated_by == users_table.c.id,
                                    projects_table.c.updated_by == users_table.c.username,
                                )
                            )
                        )
                        .where(projects_table.c.id == project_id)
                    ).mappings().first()
                    if not row:
                        self._send_json({"success": False, "error": "Project not found"}, 404)
                        return
                    import json
                    display_name = row.get("updated_by_display_name") or row.get("updated_by_username") or row.get("updated_by") or ''
                    self._send_json({
                        "success": True,
                        "project": {
                            "id": row["id"],
                            "slug": row["slug"],
                            "name": row["name"],
                            "current_state": json.loads(row["current_state_json"] or '{}'),
                            "state_version": row["state_version"],
                            "updated_by": row["updated_by"],
                            "updated_by_display_name": display_name,
                            "updated_at": row["updated_at"],
                            "created_at": row["created_at"],
                        }
                    })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == '/config':
            self._send_json({
                "save_path": config["save_path"],
                "image_save_path": config["image_save_path"] or config["save_path"],
                "video_save_path": config["video_save_path"] or config["save_path"],
                "image_save_path_raw": config["image_save_path"],
                "video_save_path_raw": config["video_save_path"],
                "auto_create_dir": config["auto_create_dir"],
                "allow_overwrite": config["allow_overwrite"],
                "convert_png_to_jpg": config["convert_png_to_jpg"],
                "jpg_quality": config["jpg_quality"],
                "proxy_allowed_hosts": config.get("proxy_allowed_hosts", []),
                "proxy_timeout": config.get("proxy_timeout", DEFAULT_PROXY_TIMEOUT),
                "pil_available": PIL_AVAILABLE
            })
            return

        if path == '/list-files':
            if db_manager.enabled:
                rows = db_manager.list_assets()
                files = []
                for row in rows:
                    files.append({
                        "id": row.get('id'),
                        "filename": row.get('filename'),
                        "path": f"db://{row.get('id')}",
                        "rel_path": f"db/{row.get('id')}/{row.get('filename')}",
                        "size": int(row.get('byte_size') or 0),
                        "mtime": int(row.get('created_at') or 0),
                        "mime_type": row.get('mime_type') or ''
                    })
                self._send_json({"success": True, "files": files, "base_path": "db://assets"})
                return
            base_path = config["save_path"]
            if not os.path.exists(base_path):
                self._send_json({"success": True, "files": [], "base_path": base_path})
                return
            files = []
            for root, dirs, filenames in os.walk(base_path):
                for filename in filenames:
                    if not (is_image_file(filename) or is_video_file(filename)):
                        continue
                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, base_path)
                    files.append({
                        "filename": filename,
                        "path": filepath.replace('\\', '/'),
                        "rel_path": rel_path.replace('\\', '/'),
                        "size": os.path.getsize(filepath),
                        "mtime": os.path.getmtime(filepath)
                    })
            self._send_json({"success": True, "files": files, "base_path": base_path.replace('\\', '/')})
            return

        # API配置路由
        if path == '/api-config':
            self.handle_get_api_config()
            return

        if path.startswith('/file/'):
            # 本地文件访问 (/file/download/image.png)
            self.handle_file_serve(path[6:])  # strip '/file/'
            return

        # 3. 静态文件服务 (SPA fallback)
        if config["static_dir"]:
            self.handle_static_file(path)
            return

        self._send_json({"error": "Endpoint not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        self._load_server_config()

        # 1. ComfyUI 路由
        if (path.startswith('/comfy/')
            or path.startswith('/w/v1/webapp/task/openapi')
            or path.startswith('/task/openapi')) and FEATURES['comfy_middleware']:
            self.handle_comfy_post(path)
            return

        if path in ('/proxy', '/proxy/'):
            self.handle_proxy(parsed)
            return

        # API配置路由
        if path == '/api-config':
            self.handle_post_api_config()
            return

        if path == '/auth/login':
            body = self._read_json_body()
            if body is None:
                self._send_json({"success": False, "error": "Invalid JSON"}, 400)
                return
            username = (body.get('username') or '').strip()
            password = body.get('password') or ''
            if not db_manager.enabled:
                self._send_json({"success": False, "error": "Database not enabled"}, 503)
                return
            result = db_manager.authenticate(username, password)
            if not result:
                self._send_json({"success": False, "error": "用户名或密码错误"}, 401)
                return
            self._send_json({"success": True, **result})
            return

        if path == '/auth/logout':
            token = self._extract_bearer_token()
            if token and db_manager.enabled:
                db_manager.revoke_token(token)
            self._send_json({"success": True})
            return

        if path == '/admin/users':
            if not db_manager.enabled:
                self._send_json({"success": False, "error": "Database not enabled"}, 503)
                return
            admin_user = self._require_admin()
            if not admin_user:
                return
            body = self._read_json_body()
            if body is None:
                self._send_json({"success": False, "error": "Invalid JSON"}, 400)
                return
            username = (body.get('username') or '').strip()
            password = body.get('password') or ''
            display_name = (body.get('display_name') or '').strip()
            try:
                user = db_manager.create_user_for_admin(username=username, password=password, display_name=display_name)
                self._audit(admin_user, 'user_create', 'user', user.get('id') or '', {
                    'username': user.get('username')
                })
                self._send_json({"success": True, "user": user})
            except ValueError as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path.startswith('/admin/users/') and path.endswith('/password'):
            if not db_manager.enabled:
                self._send_json({"success": False, "error": "Database not enabled"}, 503)
                return
            admin_user = self._require_admin()
            if not admin_user:
                return
            body = self._read_json_body()
            if body is None:
                self._send_json({"success": False, "error": "Invalid JSON"}, 400)
                return
            new_password = body.get('new_password') or ''
            user_id = path.split('/')[-2]
            try:
                ok = db_manager.update_user_password_for_admin(user_id, new_password)
                if not ok:
                    self._send_json({"success": False, "error": "User not found"}, 404)
                    return
                self._audit(admin_user, 'user_password_change', 'user', user_id)
                self._send_json({"success": True})
            except ValueError as e:
                self._send_json({"success": False, "error": str(e)}, 400)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == '/projects':
            user = self._get_current_user() if db_manager.enabled else None
            if db_manager.enabled and not user:
                self._send_json({"success": False, "error": "Unauthorized"}, 401)
                return
            body = self._read_json_body()
            if body is None:
                self._send_json({"success": False, "error": "Invalid JSON"}, 400)
                return
            name = (body.get('name') or '').strip()
            if not name:
                self._send_json({"success": False, "error": "Project name is required"}, 400)
                return
            if not db_manager.enabled:
                self._send_json({"success": False, "error": "Database not enabled"}, 503)
                return
            try:
                import uuid
                import time
                project_id = str(uuid.uuid4())
                slug = name.lower().replace(' ', '-').replace('_', '-')[:128]
                now = int(time.time())
                with db_manager.connection() as conn:
                    from sqlalchemy import select
                    # Check if slug exists
                    existing = conn.execute(
                        select(db_manager.projects).where(db_manager.projects.c.slug == slug)
                    ).first()
                    if existing:
                        slug = f"{slug}-{project_id[:8]}"
                    conn.execute(db_manager.projects.insert().values(
                        id=project_id,
                        slug=slug,
                        name=name,
                        current_state_json='{}',
                        state_version=0,
                        updated_by=user.get('id') if user else None,
                        updated_at=now,
                        created_at=now,
                    ))
                self._audit(user, 'project_create', 'project', project_id, {'name': name})
                self._send_json({
                    "success": True,
                    "project": {
                        "id": project_id,
                        "slug": slug,
                        "name": name,
                        "state_version": 0,
                        "updated_by": user.get('id') if user else None,
                        "updated_by_display_name": (user.get('display_name') or user.get('username') or '') if user else '',
                        "updated_at": now,
                        "created_at": now,
                    }
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path.startswith('/projects/'):
            # Handle project save/update
            user = self._get_current_user() if db_manager.enabled else None
            if db_manager.enabled and not user:
                self._send_json({"success": False, "error": "Unauthorized"}, 401)
                return
            body = self._read_json_body()
            if body is None:
                self._send_json({"success": False, "error": "Invalid JSON"}, 400)
                return
            project_id = path.split('/')[-1]
            if not db_manager.enabled:
                self._send_json({"success": False, "error": "Database not enabled"}, 503)
                return
            try:
                import json
                import time
                from sqlalchemy import select
                
                with db_manager.connection() as conn:
                    row = conn.execute(
                        select(db_manager.projects).where(db_manager.projects.c.id == project_id)
                    ).mappings().first()
                    if not row:
                        self._send_json({"success": False, "error": "Project not found"}, 404)
                        return
                    
                    # Update project state if provided
                    current_state = body.get('current_state')
                    if current_state is not None:
                        state_json = json.dumps(current_state, ensure_ascii=False)
                        new_version = row["state_version"] + 1
                        now = int(time.time())
                        conn.execute(
                            db_manager.projects.update()
                            .where(db_manager.projects.c.id == project_id)
                            .values(
                                current_state_json=state_json,
                                state_version=new_version,
                                updated_by=user.get('id') if user else None,
                                updated_at=now
                            )
                        )
                        self._audit(user, 'project_save', 'project', project_id, {
                            'version': new_version,
                            'name': row['name']
                        })
                        self._send_json({
                            "success": True,
                            "project": {
                                "id": project_id,
                                "state_version": new_version,
                                "updated_by": user.get('id') if user else None,
                                "updated_by_display_name": (user.get('display_name') or user.get('username') or '') if user else '',
                                "updated_at": now,
                            }
                        })
                    else:
                        # Just update metadata
                        updates = {}
                        if 'name' in body:
                            updates['name'] = body['name']
                        if updates:
                            updates['updated_at'] = int(time.time())
                            updates['updated_by'] = user.get('id') if user else None
                            conn.execute(
                                db_manager.projects.update()
                                .where(db_manager.projects.c.id == project_id)
                                .values(**updates)
                            )
                        self._send_json({"success": True})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == '/workflows/save-version':
            user = self._require_user()
            if not user:
                return
            body = self._read_json_body()
            if body is None:
                self._send_json({"success": False, "error": "Invalid JSON"}, 400)
                return
            name = (body.get('name') or '').strip()
            content = body.get('content') or {}
            save_type = body.get('save_type') or 'manual'
            comment = body.get('comment') or ''
            if not name:
                self._send_json({"success": False, "error": "workflow name required"}, 400)
                return
            if not db_manager.enabled:
                self._send_json({"success": False, "error": "Database not enabled"}, 503)
                return
            result = db_manager.save_workflow_version(
                name=name,
                content=content,
                saved_by=user.get('id'),
                save_type=save_type,
                comment=comment,
            )
            self._audit(user, 'workflow_save_version', 'workflow', result.get('workflow_id') or '', {
                'name': name,
                'version_no': result.get('version_no'),
                'save_type': save_type,
            })
            self._send_json({"success": True, "data": result})
            return

        # 2. 原有功能路由 (Save)
        body = self._read_json_body()
        if body is None and path != '/proxy':
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        if path == '/save':
            self.handle_save(body)
        elif path == '/save-batch':
            self.handle_batch_save(body)
        elif path == '/save-thumbnail':
            self.handle_save_thumbnail(body)
        elif path == '/save-cache':
            self.handle_save_cache(body)
        elif path == '/delete-file':
            self.handle_delete_file(body)
        elif path == '/delete-batch':
            self.handle_delete_batch(body)
        elif path == '/config':
            self.handle_update_config(body)
        else:
            self._send_json({"error": "Endpoint not found"}, 404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/proxy', '/proxy/'):
            self.handle_proxy(parsed)
            return
        self._send_json({"error": "Endpoint not found"}, 404)

    def do_PATCH(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/proxy', '/proxy/'):
            self.handle_proxy(parsed)
            return
        self._send_json({"error": "Endpoint not found"}, 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/admin/users/'):
            if not db_manager.enabled:
                self._send_json({"success": False, "error": "Database not enabled"}, 503)
                return
            admin_user = self._require_admin()
            if not admin_user:
                return
            user_id = path.split('/')[-1]
            if user_id == (admin_user.get('id') or ''):
                self._send_json({"success": False, "error": "不能删除当前登录的管理员账户"}, 400)
                return
            try:
                ok = db_manager.delete_user_for_admin(user_id)
                if not ok:
                    self._send_json({"success": False, "error": "User not found"}, 404)
                    return
                self._audit(admin_user, 'user_delete', 'user', user_id)
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return
        
        if path.startswith('/projects/'):
            user = self._get_current_user() if db_manager.enabled else None
            if db_manager.enabled and not user:
                self._send_json({"success": False, "error": "Unauthorized"}, 401)
                return
            project_id = path.split('/')[-1]
            if not db_manager.enabled:
                self._send_json({"success": False, "error": "Database not enabled"}, 503)
                return
            try:
                from sqlalchemy import select
                with db_manager.connection() as conn:
                    row = conn.execute(
                        select(db_manager.projects).where(db_manager.projects.c.id == project_id)
                    ).mappings().first()
                    if not row:
                        self._send_json({"success": False, "error": "Project not found"}, 404)
                        return
                    if (row.get('slug') or '') == 'default-project':
                        self._send_json({"success": False, "error": "默认项目不可删除"}, 400)
                        return
                    conn.execute(
                        db_manager.projects.delete().where(db_manager.projects.c.id == project_id)
                    )
                self._audit(user, 'project_delete', 'project', project_id, {'name': row['name']})
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return
        
        if parsed.path in ('/proxy', '/proxy/'):
            self.handle_proxy(parsed)
            return
        self._send_json({"error": "Endpoint not found"}, 404)

    # --- ComfyUI Handlers ---

    def handle_comfy_get(self, path, parsed):
        import uuid
        if path == '/comfy/apps':
            if db_manager.enabled:
                apps = [w.get('name') for w in db_manager.list_workflows() if w.get('name')]
                self._send_json({"apps": apps})
                return
            apps = []
            from config import WORKFLOWS_DIR
            if os.path.exists(WORKFLOWS_DIR):
                apps = [d for d in os.listdir(WORKFLOWS_DIR) if os.path.isdir(os.path.join(WORKFLOWS_DIR, d))]
            self._send_json({"apps": apps})

        elif path.startswith('/comfy/status/'):
            job_id = path.split('/')[-1]
            status = resolve_job_by_request_id(job_id)
            if status:
                self._send_json(status)
            else:
                self._send_json({"error": "Job not found"}, 404)

        elif path.startswith('/comfy/outputs/'):
            job_id = path.split('/')[-1]
            job = resolve_job_by_request_id(job_id)
            if job:
                self._send_json(build_outputs_response(job))
            else:
                self._send_json({"code": 404, "message": "Job not found"}, 404)

        elif path in ('/comfy/detail', '/w/v1/webapp/task/openapi/detail', '/task/openapi/detail'):
            params = parse_qs(parsed.query or '')
            request_id = params.get('requestId', [None])[0] or params.get('request_id', [None])[0] or params.get('taskId', [None])[0]
            job = resolve_job_by_request_id(request_id)
            if job:
                self._send_json(build_detail_response(job))
            else:
                self._send_json({"code": 404, "message": "Job not found"}, 404)

        elif path in ('/comfy/outputs', '/w/v1/webapp/task/openapi/outputs', '/task/openapi/outputs'):
            params = parse_qs(parsed.query or '')
            request_id = params.get('requestId', [None])[0] or params.get('request_id', [None])[0] or params.get('taskId', [None])[0]
            job = resolve_job_by_request_id(request_id)
            if job:
                self._send_json(build_outputs_response(job))
            else:
                self._send_json({"code": 404, "message": "Job not found"}, 404)

    def handle_comfy_post(self, path):
        import uuid
        import time
        if path in ('/comfy/queue', '/task/openapi/create', '/task/openapi/ai-app/run', '/w/v1/webapp/task/openapi/create'):
            body = self._read_json_body()
            if body is None:
                self._send_json({"error": "Invalid JSON"}, 400)
                return

            app_id = body.get('app_id') or body.get('web_app_id') or body.get('webappId') or body.get('workflow_id') or body.get('appId')
            params = body.get('input_values') or body.get('inputs') or body.get('nodeInfoList') or {}
            raw_prompt = body.get('prompt') if isinstance(body.get('prompt'), dict) else None

            if not app_id and not raw_prompt:
                self._send_json({"code": 400, "message": "Missing app_id or prompt"}, 400)
                return

            job_id = str(uuid.uuid4())
            job = {
                "id": job_id,
                "app_id": app_id,
                "inputs": params,
                "prompt": raw_prompt,
                "status": "queued",
                "created_at": time.time()
            }

            with STATUS_LOCK:
                JOB_STATUS[job_id] = job
            JOB_QUEUE.put(job)

            log(f"[Comfy] 接收任务: {job_id}")
            self._send_json({
                "code": 20000,
                "message": "Ok",
                "status": True,
                "requestId": job_id,
                "request_id": job_id,
                "job_id": job_id,
                "taskId": job_id,
                "data": {
                    "requestId": job_id,
                    "taskId": job_id,
                    "status": "Queued"
                }
            })

    # --- File Save Handlers ---

    def handle_save(self, data):
        """处理单个文件保存"""
        try:
            user = self._get_current_user() if db_manager.enabled else None
            if db_manager.enabled and not user:
                self._send_json({"success": False, "error": "Unauthorized"}, 401)
                return
            filename = data.get('filename', '')
            content = data.get('content', '')
            url = data.get('url', '')
            subfolder = data.get('subfolder', '')
            custom_path = data.get('path', '')

            if not filename and not custom_path:
                self._send_json({"success": False, "error": "缺少文件名"}, 400)
                return

            if custom_path:
                custom_path = os.path.expanduser(custom_path)
                if not os.path.isabs(custom_path):
                    custom_path = safe_join(config["save_path"], custom_path)
                    if not custom_path:
                        self._send_json({"success": False, "error": "非法路径"}, 400)
                        return
                else:
                    custom_path = os.path.abspath(custom_path)
                if not is_path_allowed(custom_path):
                    self._send_json({"success": False, "error": "不允许保存到该路径"}, 403)
                    return
                save_dir = os.path.dirname(custom_path)
                filepath = custom_path
            else:
                if subfolder:
                    save_dir = safe_join(config["save_path"], subfolder)
                    if not save_dir:
                        self._send_json({"success": False, "error": "非法子目录"}, 400)
                        return
                else:
                    save_dir = config["save_path"]
                filepath = os.path.join(save_dir, filename)

            if config["auto_create_dir"]:
                ensure_dir(save_dir)
            elif not os.path.exists(save_dir):
                self._send_json({"success": False, "error": f"目录不存在: {save_dir}"}, 400)
                return

            if not config["allow_overwrite"]:
                filepath = get_unique_filename(filepath)

            if content:
                if ',' in content:
                    content = content.split(',', 1)[1]
                file_data = base64.b64decode(content)
            elif url:
                with urllib.request.urlopen(url) as response:
                    file_data = response.read()
            else:
                self._send_json({"success": False, "error": "缺少文件内容"}, 400)
                return

            if db_manager.enabled:
                ext = os.path.splitext(filename or '')[1].lower()
                mime_type = mimetypes.types_map.get(ext) or 'application/octet-stream'
                asset_type = 'video' if is_video_file(filename) else ('image' if is_image_file(filename) else 'text')
                saved = db_manager.save_asset(
                    asset_type=asset_type,
                    filename=filename or f"asset-{uuid.uuid4().hex}{ext or '.bin'}",
                    mime_type=mime_type,
                    content=file_data,
                    created_by=user.get('id') if user else None,
                    meta={"source_url": url or "", "subfolder": subfolder or ""},
                )
                self._audit(user, 'asset_save', 'asset', saved.get('id') or '', {
                    'filename': saved.get('filename'),
                    'size': saved.get('size'),
                })
                self._send_json({
                    "success": True,
                    "message": "文件保存成功",
                    "path": f"db://{saved.get('id')}",
                    "asset_id": saved.get('id'),
                    "url": f"http://127.0.0.1:{config['port']}{saved.get('url')}",
                    "rel_path": saved.get('rel_path'),
                    "size": saved.get('size')
                })
                return

            with open(filepath, 'wb') as f:
                f.write(file_data)

            log(f"文件已保存: {filepath} ({len(file_data)} bytes)")
            self._send_json({
                "success": True,
                "message": "文件保存成功",
                "path": filepath,
                "size": len(file_data)
            })
        except Exception as e:
            log(f"文件保存失败: {e}")
            self._send_json({"success": False, "error": str(e)}, 500)

    def handle_batch_save(self, data):
        """处理批量文件保存"""
        user = self._get_current_user() if db_manager.enabled else None
        if db_manager.enabled and not user:
            self._send_json({"success": False, "error": "Unauthorized"}, 401)
            return
        files = data.get('files', [])
        if not files:
            self._send_json({"success": True, "saved_count": 0, "results": []})
            return
        results = []
        for item in files:
            try:
                filename = item.get('filename', '')
                content = item.get('content', '')
                url = item.get('url', '')
                subfolder = item.get('subfolder', '')
                custom_path = item.get('path', '')

                if not filename and not custom_path:
                    results.append({"success": False, "error": "缺少文件名"})
                    continue

                if custom_path:
                    custom_path = os.path.expanduser(custom_path)
                    if not os.path.isabs(custom_path):
                        custom_path = safe_join(config["save_path"], custom_path)
                        if not custom_path:
                            results.append({"success": False, "error": "非法路径"})
                            continue
                    else:
                        custom_path = os.path.abspath(custom_path)
                    if not is_path_allowed(custom_path):
                        results.append({"success": False, "error": "不允许保存到该路径"})
                        continue
                    save_dir = os.path.dirname(custom_path)
                    filepath = custom_path
                else:
                    if subfolder:
                        save_dir = safe_join(config["save_path"], subfolder)
                        if not save_dir:
                            results.append({"success": False, "error": "非法子目录"})
                            continue
                    else:
                        save_dir = config["save_path"]
                    filepath = os.path.join(save_dir, filename)

                if config["auto_create_dir"]:
                    ensure_dir(save_dir)
                elif not os.path.exists(save_dir):
                    results.append({"success": False, "error": f"目录不存在: {save_dir}"})
                    continue

                if not config["allow_overwrite"]:
                    filepath = get_unique_filename(filepath)

                if content:
                    if ',' in content:
                        content = content.split(',', 1)[1]
                    file_data = base64.b64decode(content)
                elif url:
                    with urllib.request.urlopen(url) as response:
                        file_data = response.read()
                else:
                    results.append({"success": False, "error": "缺少文件内容"})
                    continue

                if db_manager.enabled:
                    ext = os.path.splitext(filename or '')[1].lower()
                    mime_type = mimetypes.types_map.get(ext) or 'application/octet-stream'
                    asset_type = 'video' if is_video_file(filename) else ('image' if is_image_file(filename) else 'text')
                    saved = db_manager.save_asset(
                        asset_type=asset_type,
                        filename=filename or f"asset-{uuid.uuid4().hex}{ext or '.bin'}",
                        mime_type=mime_type,
                        content=file_data,
                        created_by=user.get('id') if user else None,
                        meta={"source_url": url or "", "subfolder": subfolder or ""},
                    )
                    self._audit(user, 'asset_save', 'asset', saved.get('id') or '', {
                        'filename': saved.get('filename'),
                        'size': saved.get('size'),
                        'batch': True,
                    })
                    results.append({
                        "success": True,
                        "asset_id": saved.get('id'),
                        "path": f"db://{saved.get('id')}",
                        "rel_path": saved.get('rel_path'),
                        "url": f"http://127.0.0.1:{config['port']}{saved.get('url')}",
                        "size": saved.get('size')
                    })
                    continue

                with open(filepath, 'wb') as f:
                    f.write(file_data)

                results.append({"success": True, "path": filepath, "size": len(file_data)})
            except Exception as e:
                results.append({"success": False, "error": str(e)})
        saved_count = sum(1 for r in results if r.get('success'))
        self._send_json({
            "success": True,
            "saved_count": saved_count,
            "results": results
        })

    def handle_delete_file(self, data):
        """处理文件删除"""
        user = self._get_current_user() if db_manager.enabled else None
        if db_manager.enabled and not user:
            self._send_json({"success": False, "error": "Unauthorized"}, 401)
            return
        if db_manager.enabled:
            asset_id = (data.get('asset_id') or '').strip()
            if not asset_id:
                path_field = (data.get('path') or '').strip()
                if path_field.startswith('db://'):
                    asset_id = path_field.replace('db://', '', 1)
                url_field = data.get('url') or ''
                marker = '/file/db/'
                if not asset_id and marker in url_field:
                    tail = url_field.split(marker, 1)[1]
                    asset_id = tail.split('/', 1)[0]
            if not asset_id:
                self._send_json({"success": False, "error": "缺少 asset_id"}, 400)
                return
            if db_manager.delete_asset(asset_id, user.get('id') if user else None):
                self._audit(user, 'asset_delete', 'asset', asset_id, {})
                self._send_json({"success": True})
            else:
                self._send_json({"success": False, "error": "Asset not found"}, 404)
            return
        path = data.get('path', '')
        url = data.get('url', '')
        if not path and url and url.startswith(f"http://127.0.0.1:{config['port']}/file/"):
            rel_path = url.replace(f"http://127.0.0.1:{config['port']}/file/", '')
            rel_path = normalize_rel_path(rel_path)
            if rel_path:
                path = os.path.join(config["save_path"], rel_path)
        if not path or not is_path_allowed(path):
            self._send_json({"error": "Invalid path or permission denied"}, 403)
            return
        try:
            if os.path.exists(path):
                os.remove(path)
                log(f"文件删除: {path}")
                self._send_json({"success": True})
            else:
                self._send_json({"error": "File not found"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def handle_delete_batch(self, data):
        """处理批量文件删除"""
        user = self._get_current_user() if db_manager.enabled else None
        if db_manager.enabled and not user:
            self._send_json({"success": False, "error": "Unauthorized"}, 401)
            return
        if db_manager.enabled:
            files = data.get('files', [])
            if not files:
                self._send_json({"success": False, "error": "没有要删除的文件"}, 400)
                return
            results = []
            for item in files:
                asset_id = ''
                if isinstance(item, dict):
                    asset_id = (item.get('asset_id') or '').strip()
                    if not asset_id and isinstance(item.get('path'), str) and item.get('path').startswith('db://'):
                        asset_id = item.get('path').replace('db://', '', 1)
                elif isinstance(item, str) and item.startswith('db://'):
                    asset_id = item.replace('db://', '', 1)
                if not asset_id:
                    results.append({"path": item, "success": False, "error": "缺少 asset_id"})
                    continue
                ok = db_manager.delete_asset(asset_id, user.get('id') if user else None)
                results.append({"asset_id": asset_id, "success": bool(ok)})
                if ok:
                    self._audit(user, 'asset_delete', 'asset', asset_id, {'batch': True})
            success_count = sum(1 for r in results if r.get('success'))
            self._send_json({
                "success": True,
                "message": f"已删除 {success_count}/{len(files)} 个文件",
                "results": results
            })
            return
        files = data.get('files', [])
        if not files:
            self._send_json({"success": False, "error": "没有要删除的文件"}, 400)
            return
        results = []
        base_dirs = [config["save_path"]]
        if config["image_save_path"]:
            base_dirs.append(config["image_save_path"])
        if config["video_save_path"]:
            base_dirs.append(config["video_save_path"])
        for file_info in files:
            try:
                filepath = ''
                url = ''
                if isinstance(file_info, str):
                    filepath = file_info
                else:
                    filepath = file_info.get('path') or ''
                    url = file_info.get('url') or ''
                found_path = None
                if filepath and os.path.isabs(filepath) and os.path.exists(filepath):
                    found_path = filepath
                if not found_path and url and '/file/' in url:
                    rel_path = url.split('/file/')[-1]
                    rel_path = normalize_rel_path(rel_path)
                    if rel_path:
                        for base_dir in base_dirs:
                            check_path = os.path.join(base_dir, rel_path)
                            if os.path.exists(check_path):
                                found_path = check_path
                                break
                if not found_path and filepath and not os.path.isabs(filepath):
                    rel_path_os = filepath.replace('/', os.sep)
                    for base_dir in base_dirs:
                        check_path = os.path.join(base_dir, rel_path_os)
                        if os.path.exists(check_path):
                            found_path = check_path
                            break
                if not found_path:
                    results.append({"path": filepath or url, "success": False, "error": "文件不存在"})
                    continue
                abs_path = os.path.abspath(found_path)
                allowed = any(abs_path.startswith(os.path.abspath(d)) for d in base_dirs)
                if not allowed:
                    ext = os.path.splitext(abs_path)[1].lower()
                    if ext in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mov', '.webm'}:
                        allowed = True
                if not allowed:
                    results.append({"path": found_path, "success": False, "error": "不允许删除"})
                    continue
                os.remove(found_path)
                results.append({"path": found_path, "success": True})
            except Exception as e:
                results.append({"path": filepath or url, "success": False, "error": str(e)})
        success_count = sum(1 for r in results if r.get('success'))
        self._send_json({
            "success": True,
            "message": f"已删除 {success_count}/{len(files)} 个文件",
            "results": results
        })

    def handle_update_config(self, data):
        """处理配置更新"""
        user = self._get_current_user() if db_manager.enabled else None
        if db_manager.enabled and not user:
            self._send_json({"success": False, "error": "Unauthorized"}, 401)
            return
        # 简单的配置更新逻辑
        if 'save_path' in data:
            config['save_path'] = data['save_path']
        if 'image_save_path' in data:
            config['image_save_path'] = data['image_save_path'] or ''
        if 'video_save_path' in data:
            config['video_save_path'] = data['video_save_path'] or ''
        if 'log_enabled' in data:
            # 仅在明确提供布尔值时更新，避免 null/空字符串误关闭日志
            if isinstance(data['log_enabled'], bool):
                config['log_enabled'] = data['log_enabled']
        if 'convert_png_to_jpg' in data:
            config['convert_png_to_jpg'] = bool(data['convert_png_to_jpg'])
        if 'jpg_quality' in data:
            try:
                config['jpg_quality'] = int(data['jpg_quality'])
            except Exception:
                pass
        if 'proxy_allowed_hosts' in data and isinstance(data['proxy_allowed_hosts'], list):
            config['proxy_allowed_hosts'] = data['proxy_allowed_hosts']
        if 'proxy_timeout' in data:
            try:
                config['proxy_timeout'] = int(data['proxy_timeout'])
            except Exception:
                pass
        if db_manager.enabled:
            db_manager.upsert_config('server_config', {
                "save_path": config["save_path"],
                "image_save_path": config["image_save_path"],
                "video_save_path": config["video_save_path"],
                "auto_create_dir": config["auto_create_dir"],
                "allow_overwrite": config["allow_overwrite"],
                "convert_png_to_jpg": config["convert_png_to_jpg"],
                "jpg_quality": config["jpg_quality"],
                "proxy_allowed_hosts": config.get("proxy_allowed_hosts", []),
                "proxy_timeout": config.get("proxy_timeout", DEFAULT_PROXY_TIMEOUT),
                "log_enabled": config.get("log_enabled", True)
            }, user.get('id') if user else None)
            self._audit(user, 'config_update', 'system_config', 'server_config', data)
        log("配置已更新")
        self._send_json({"success": True, "config": config})

    def handle_save_thumbnail(self, data):
        """处理缩略图保存"""
        try:
            user = self._get_current_user() if db_manager.enabled else None
            if db_manager.enabled and not user:
                self._send_json({"success": False, "error": "Unauthorized"}, 401)
                return
            item_id = data.get('id', '')
            content = data.get('content', '')
            category = data.get('category', 'history')
            if not item_id or not content:
                self._send_json({"success": False, "error": "缺少ID或内容"}, 400)
                return
            cache_dir = os.path.join(config["save_path"], '.tapnow_cache', category)
            ensure_dir(cache_dir)
            filename = f"{item_id}.jpg"
            filepath = os.path.join(cache_dir, filename)
            if ',' in content:
                content = content.split(',', 1)[1]
            file_data = base64.b64decode(content)
            if db_manager.enabled:
                saved = db_manager.save_asset(
                    asset_type='image',
                    filename=f"{item_id}.jpg",
                    mime_type='image/jpeg',
                    content=file_data,
                    created_by=user.get('id') if user else None,
                    meta={"category": category, "thumbnail": True},
                )
                self._audit(user, 'asset_save', 'asset', saved.get('id') or '', {"thumbnail": True, "category": category})
                self._send_json({
                    "success": True,
                    "path": f"db://{saved.get('id')}",
                    "url": f"http://127.0.0.1:{config['port']}{saved.get('url')}",
                    "rel_path": saved.get('rel_path'),
                    "asset_id": saved.get('id')
                })
                return
            with open(filepath, 'wb') as f:
                f.write(file_data)
            rel_path = f".tapnow_cache/{category}/{filename}"
            local_url = f"http://127.0.0.1:{config['port']}/file/{rel_path}"
            self._send_json({
                "success": True,
                "path": filepath,
                "url": local_url,
                "rel_path": rel_path
            })
        except Exception as e:
            log(f"[save-cache] 保存失败: {e}")
            self._send_json({"success": False, "error": str(e)}, 500)

    def handle_save_cache(self, data):
        """处理缓存保存"""
        try:
            user = self._get_current_user() if db_manager.enabled else None
            if db_manager.enabled and not user:
                self._send_json({"success": False, "error": "Unauthorized"}, 401)
                return
            item_id = data.get('id', '')
            content = data.get('content', '')
            category = data.get('category', 'characters')
            filename_ext = data.get('ext', '.jpg')
            file_type = data.get('type', 'image')
            custom_path = data.get('custom_path', '')
            if not item_id or not content:
                self._send_json({"success": False, "error": "缺少ID或内容"}, 400)
                return
            if custom_path:
                cache_dir = os.path.expanduser(custom_path)
                if not os.path.isabs(cache_dir):
                    cache_dir = safe_join(config["save_path"], cache_dir)
                    if not cache_dir:
                        self._send_json({"success": False, "error": "非法路径"}, 400)
                        return
                else:
                    cache_dir = os.path.abspath(cache_dir)
                if not is_path_allowed(cache_dir):
                    self._send_json({"success": False, "error": "不允许保存到该路径"}, 403)
                    return
                base_root = config["save_path"]
            elif file_type == 'video' and config["video_save_path"]:
                base_root = config["video_save_path"]
                cache_dir = os.path.join(base_root, category)
            elif file_type == 'image' and config["image_save_path"]:
                base_root = config["image_save_path"]
                cache_dir = os.path.join(base_root, category)
            else:
                base_root = config["save_path"]
                cache_dir = os.path.join(base_root, '.tapnow_cache', category)
            ensure_dir(cache_dir)
            if ',' in content:
                content = content.split(',', 1)[1]
            file_data = base64.b64decode(content)
            converted = False
            if file_type == 'image' and config["convert_png_to_jpg"] and filename_ext.lower() == '.png':
                file_data, converted = convert_png_to_jpg(file_data, config["jpg_quality"])
                if converted:
                    filename_ext = '.jpg'
            filename = f"{item_id}{filename_ext}"
            if db_manager.enabled:
                mime_type = mimetypes.types_map.get(filename_ext.lower()) or ('video/mp4' if file_type == 'video' else 'image/jpeg')
                saved = db_manager.save_asset(
                    asset_type='video' if file_type == 'video' else 'image',
                    filename=filename,
                    mime_type=mime_type,
                    content=file_data,
                    created_by=user.get('id') if user else None,
                    meta={"category": category, "converted": converted, "file_type": file_type},
                )
                self._audit(user, 'asset_save', 'asset', saved.get('id') or '', {
                    "category": category,
                    "type": file_type,
                    "converted": converted
                })
                self._send_json({
                    "success": True,
                    "path": f"db://{saved.get('id')}",
                    "url": f"http://127.0.0.1:{config['port']}{saved.get('url')}",
                    "rel_path": saved.get('rel_path'),
                    "asset_id": saved.get('id'),
                    "converted": converted,
                    "size": len(file_data)
                })
                return
            filepath = os.path.join(cache_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(file_data)
            try:
                rel_path = os.path.relpath(filepath, base_root).replace('\\', '/')
            except ValueError:
                rel_path = os.path.relpath(filepath, cache_dir).replace('\\', '/')
                if base_root == config["save_path"]:
                    rel_path = f".tapnow_cache/{category}/{rel_path}"
                else:
                    rel_path = f"{category}/{rel_path}"
            if rel_path.startswith('..'):
                rel_path = os.path.relpath(filepath, cache_dir).replace('\\', '/')
                if base_root == config["save_path"]:
                    rel_path = f".tapnow_cache/{category}/{rel_path}"
                else:
                    rel_path = f"{category}/{rel_path}"
            local_url = f"http://127.0.0.1:{config['port']}/file/{rel_path}"
            self._send_json({
                "success": True,
                "path": filepath,
                "url": local_url,
                "rel_path": rel_path,
                "converted": converted,
                "size": len(file_data)
            })
        except Exception as e:
            log(f"[save-cache] 保存失败: {e}")
            self._send_json({"success": False, "error": str(e)}, 500)

    def handle_file_serve(self, rel_path):
        """处理文件服务"""
        rel_path = normalize_rel_path(rel_path)
        log(f"[FileServe] 请求路径: {rel_path}")
        if not rel_path:
            self.send_response(400)
            self.end_headers()
            return
        if db_manager.enabled:
            parts = (rel_path or '').replace('\\', '/').split('/')
            if len(parts) >= 2 and parts[0] == 'db':
                asset_id = parts[1]
                asset = db_manager.get_asset(asset_id)
                if not asset:
                    self.send_response(404)
                    self.end_headers()
                    return
                payload = asset.get('content_blob') or b''
                content_type = asset.get('mime_type') or 'application/octet-stream'
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Cache-Control', LOCAL_FILE_CACHE_CONTROL)
                self._send_cors()
                self.end_headers()
                if self.command != 'HEAD':
                    self.wfile.write(payload)
                return
        candidates = [
            os.path.join(config["save_path"], rel_path),
        ]
        if config["image_save_path"]:
            candidates.append(os.path.join(config["image_save_path"], rel_path))
        if config["video_save_path"]:
            candidates.append(os.path.join(config["video_save_path"], rel_path))
        filepath = None
        for candidate in candidates:
            log(f"[FileServe] 检查: {candidate} -> 存在:{os.path.exists(candidate)} 文件:{os.path.isfile(candidate) if os.path.exists(candidate) else False}")
            if os.path.exists(candidate) and os.path.isfile(candidate):
                filepath = candidate
                break
        if not filepath:
            log(f"[FileServe] 文件未找到: {rel_path}")
            self.send_response(404)
            self.end_headers()
            return
        try:
            stat = os.stat(filepath)
            etag = f"\"{int(stat.st_mtime)}-{stat.st_size}\""
            if_match = self.headers.get('If-None-Match', '')
            if if_match == etag:
                self.send_response(304)
                self.send_header('ETag', etag)
                self.send_header('Cache-Control', LOCAL_FILE_CACHE_CONTROL)
                self.send_header('Last-Modified', formatdate(stat.st_mtime, usegmt=True))
                self._send_cors()
                self.end_headers()
                return
            content_type, _ = mimetypes.guess_type(filepath)
            if not content_type:
                if filepath.endswith('.png'):
                    content_type = 'image/png'
                elif filepath.endswith('.jpg') or filepath.endswith('.jpeg'):
                    content_type = 'image/jpeg'
                elif filepath.endswith('.webp'):
                    content_type = 'image/webp'
                elif filepath.endswith('.gif'):
                    content_type = 'image/gif'
                elif filepath.endswith('.mp4'):
                    content_type = 'video/mp4'
                elif filepath.endswith('.webm'):
                    content_type = 'video/webm'
                else:
                    content_type = 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(stat.st_size))
            self.send_header('ETag', etag)
            self.send_header('Last-Modified', formatdate(stat.st_mtime, usegmt=True))
            self.send_header('Cache-Control', LOCAL_FILE_CACHE_CONTROL)
            self._send_cors()
            self.end_headers()
            if self.command == 'HEAD':
                return
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as e:
            log(f"[FileServe] 错误: {e}, 路径: {filepath}")
            try:
                self.send_response(500)
                self.end_headers()
            except Exception:
                pass

    def handle_static_file(self, path):
        """处理静态文件服务 (SPA fallback)"""
        static_dir = config.get("static_dir", "")
        if not static_dir or not os.path.isdir(static_dir):
            self._send_json({"error": "Static directory not configured"}, 500)
            return

        # 清理路径，防止目录遍历攻击
        safe_path = path.lstrip('/')
        if '..' in safe_path or safe_path.startswith('.'):
            safe_path = ''

        # 尝试查找文件
        file_path = os.path.join(static_dir, safe_path)

        # 如果是目录或不存在，尝试 index.html (SPA fallback)
        if os.path.isdir(file_path) or not os.path.exists(file_path):
            index_path = os.path.join(static_dir, 'index.html')
            if os.path.exists(index_path):
                file_path = index_path
            else:
                self._send_json({"error": "Not found"}, 404)
                return

        # 检查文件是否在静态目录内 (防止目录遍历)
        try:
            real_file = os.path.realpath(file_path)
            real_static = os.path.realpath(static_dir)
            if not real_file.startswith(real_static):
                self._send_json({"error": "Access denied"}, 403)
                return
        except Exception:
            self._send_json({"error": "Invalid path"}, 400)
            return

        # 提供文件
        try:
            content_type, _ = mimetypes.guess_type(file_path)
            if not content_type:
                if file_path.endswith('.js'):
                    content_type = 'application/javascript'
                elif file_path.endswith('.css'):
                    content_type = 'text/css'
                elif file_path.endswith('.html'):
                    content_type = 'text/html'
                elif file_path.endswith('.svg'):
                    content_type = 'image/svg+xml'
                else:
                    content_type = 'application/octet-stream'

            stat = os.stat(file_path)
            etag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
            if_match = self.headers.get('If-None-Match', '')

            if if_match == etag:
                self.send_response(304)
                self.send_header('ETag', etag)
                self.send_header('Cache-Control', 'public, max-age=3600')
                self.end_headers()
                return

            with open(file_path, 'rb') as f:
                content = f.read()

            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', len(content))
            self.send_header('ETag', etag)
            self.send_header('Cache-Control', 'public, max-age=3600')
            self.send_header('Last-Modified', formatdate(stat.st_mtime, usegmt=True))
            self._send_cors()
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            log(f"静态文件服务错误: {e}")
            self._send_json({"error": "File serving failed"}, 500)

    def handle_proxy(self, parsed):
        """处理代理请求"""
        target_url = parse_proxy_target(parsed, self.headers)
        if not target_url:
            self._send_json({"success": False, "error": "缺少目标URL"}, 400)
            return
        parsed_target = urlparse(target_url)
        if parsed_target.scheme not in ('http', 'https') or not parsed_target.hostname:
            self._send_json({"success": False, "error": "非法目标URL"}, 400)
            return
        if not is_proxy_target_allowed(target_url):
            self._send_json({"success": False, "error": "目标域名不在允许列表"}, 403)
            return

        method = self.command
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        forward_headers = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in PROXY_SKIP_REQUEST_HEADERS:
                continue
            if lower in ('origin', 'referer'):
                continue
            forward_headers[key] = value
        if parsed_target.netloc:
            forward_headers['Host'] = parsed_target.netloc

        path = parsed_target.path or '/'
        if parsed_target.query:
            path = f"{path}?{parsed_target.query}"

        port = parsed_target.port or (443 if parsed_target.scheme == 'https' else 80)
        conn_class = http.client.HTTPSConnection if parsed_target.scheme == 'https' else http.client.HTTPConnection
        timeout_value = config.get("proxy_timeout", DEFAULT_PROXY_TIMEOUT)
        timeout_value = None if timeout_value == 0 else timeout_value
        try:
            conn = conn_class(parsed_target.hostname, port, timeout=timeout_value)
            conn.request(method, path, body=body, headers=forward_headers)
            resp = conn.getresponse()
        except Exception as exc:
            log(f"代理请求失败: {exc}")
            self._send_json({"success": False, "error": f"代理请求失败: {exc}"}, 502)
            try:
                conn.close()
            except Exception:
                pass
            return

        try:
            response_headers = resp.getheaders()
            content_type = ''
            for header, value in response_headers:
                if header.lower() == 'content-type':
                    content_type = value
                    break
            should_override_cache = (
                method in ('GET', 'HEAD')
                and resp.status in (200, 203, 206)
                and (is_media_content_type(content_type) or is_media_path(parsed_target.path))
            )
            self.send_response(resp.status, resp.reason)
            for header, value in response_headers:
                lower = header.lower()
                if lower in PROXY_SKIP_RESPONSE_HEADERS:
                    continue
                if should_override_cache and lower in ('cache-control', 'expires', 'pragma'):
                    continue
                self.send_header(header, value)
            if should_override_cache:
                self.send_header('Cache-Control', PROXY_MEDIA_CACHE_CONTROL)
            self._send_cors()
            self.end_headers()

            if method == 'HEAD':
                return

            for chunk in iter_proxy_response_chunks(resp):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            resp.close()
            conn.close()

    # --- API Config Handlers ---

    def handle_get_api_config(self):
        """获取API配置"""
        try:
            if db_manager.enabled:
                user = self._require_user()
                if not user:
                    return
                api_config = db_manager.get_config('api_config') or api_config_manager._get_default_config()
                self._send_json({
                    "success": True,
                    "data": api_config
                })
                return
            api_config = api_config_manager.load_config()
            self._send_json({
                "success": True,
                "data": api_config
            })
        except Exception as e:
            log(f"获取API配置失败: {e}")
            self._send_json({"success": False, "error": str(e)}, 500)

    def handle_post_api_config(self):
        """更新API配置"""
        try:
            user = self._get_current_user() if db_manager.enabled else None
            if db_manager.enabled and not user:
                self._send_json({"success": False, "error": "Unauthorized"}, 401)
                return
            body = self._read_json_body()
            if body is None:
                self._send_json({"error": "Invalid JSON"}, 400)
                return

            action = body.get('action', 'update')

            if action == 'update':
                # 完全替换配置
                config_data = body.get('config', {})
                if db_manager.enabled:
                    db_manager.upsert_config('api_config', config_data, user.get('id') if user else None)
                    self._audit(user, 'api_config_update', 'system_config', 'api_config', {'action': action})
                    self._send_json({
                        "success": True,
                        "message": "配置已保存"
                    })
                    return
                api_config_manager.save_config(config_data)
                log("API配置已更新")
                self._send_json({
                    "success": True,
                    "message": "配置已保存"
                })

            elif action == 'update_provider':
                # 更新单个provider
                provider_id = body.get('provider_id')
                provider_config = body.get('config', {})
                if not provider_id:
                    self._send_json({"success": False, "error": "缺少provider_id"}, 400)
                    return
                if db_manager.enabled:
                    cfg = db_manager.get_config('api_config') or api_config_manager._get_default_config()
                    providers = cfg.get('providers') or {}
                    providers[provider_id] = provider_config
                    cfg['providers'] = providers
                    db_manager.upsert_config('api_config', cfg, user.get('id') if user else None)
                    self._audit(user, 'api_config_update_provider', 'system_config', provider_id, {'action': action})
                    self._send_json({
                        "success": True,
                        "message": f"Provider {provider_id} 已更新"
                    })
                    return
                api_config_manager.set_provider_config(provider_id, provider_config)
                self._send_json({
                    "success": True,
                    "message": f"Provider {provider_id} 已更新"
                })

            elif action == 'update_api_key':
                # 更新API Key
                provider_id = body.get('provider_id')
                api_key = body.get('api_key', '')
                if not provider_id:
                    self._send_json({"success": False, "error": "缺少provider_id"}, 400)
                    return
                if db_manager.enabled:
                    cfg = db_manager.get_config('api_config') or api_config_manager._get_default_config()
                    keys = cfg.get('api_keys') or {}
                    keys[provider_id] = api_key
                    cfg['api_keys'] = keys
                    db_manager.upsert_config('api_config', cfg, user.get('id') if user else None)
                    self._audit(user, 'api_config_update_key', 'system_config', provider_id, {'action': action})
                    self._send_json({
                        "success": True,
                        "message": f"API Key for {provider_id} 已更新"
                    })
                    return
                api_config_manager.set_provider_api_key(provider_id, api_key)
                self._send_json({
                    "success": True,
                    "message": f"API Key for {provider_id} 已更新"
                })

            elif action == 'update_global_key':
                # 更新全局API Key
                api_key = body.get('api_key', '')
                if db_manager.enabled:
                    cfg = db_manager.get_config('api_config') or api_config_manager._get_default_config()
                    cfg['global_api_key'] = api_key
                    db_manager.upsert_config('api_config', cfg, user.get('id') if user else None)
                    self._audit(user, 'api_config_update_global', 'system_config', 'global_api_key', {'action': action})
                    self._send_json({
                        "success": True,
                        "message": "全局API Key已更新"
                    })
                    return
                api_config_manager.update_global_api_key(api_key)
                self._send_json({
                    "success": True,
                    "message": "全局API Key已更新"
                })

            elif action == 'update_features':
                # 更新功能开关
                features = body.get('features', {})
                if db_manager.enabled:
                    cfg = db_manager.get_config('api_config') or api_config_manager._get_default_config()
                    cfg['features'] = features
                    db_manager.upsert_config('api_config', cfg, user.get('id') if user else None)
                    self._audit(user, 'api_config_update_features', 'system_config', 'features', {'action': action})
                    self._send_json({
                        "success": True,
                        "message": "功能配置已更新"
                    })
                    return
                api_config_manager.update_features(features)
                self._send_json({
                    "success": True,
                    "message": "功能配置已更新"
                })

            elif action == 'delete_provider':
                # 删除provider
                provider_id = body.get('provider_id')
                if not provider_id:
                    self._send_json({"success": False, "error": "缺少provider_id"}, 400)
                    return
                if db_manager.enabled:
                    cfg = db_manager.get_config('api_config') or api_config_manager._get_default_config()
                    providers = cfg.get('providers') or {}
                    api_keys = cfg.get('api_keys') or {}
                    providers.pop(provider_id, None)
                    api_keys.pop(provider_id, None)
                    cfg['providers'] = providers
                    cfg['api_keys'] = api_keys
                    db_manager.upsert_config('api_config', cfg, user.get('id') if user else None)
                    self._audit(user, 'api_config_delete_provider', 'system_config', provider_id, {'action': action})
                    self._send_json({
                        "success": True,
                        "message": f"Provider {provider_id} 已删除"
                    })
                    return
                api_config_manager.delete_provider(provider_id)
                self._send_json({
                    "success": True,
                    "message": f"Provider {provider_id} 已删除"
                })

            elif action == 'export':
                # 导出配置
                include_keys = body.get('include_keys', True)
                if db_manager.enabled:
                    exported = db_manager.get_config('api_config') or api_config_manager._get_default_config()
                    if not include_keys:
                        exported.pop('api_keys', None)
                        exported.pop('global_api_key', None)
                    self._send_json({
                        "success": True,
                        "data": exported
                    })
                    return
                exported = api_config_manager.export_config(include_keys=include_keys)
                self._send_json({
                    "success": True,
                    "data": exported
                })

            elif action == 'import':
                # 导入配置
                config_data = body.get('config', {})
                if not config_data:
                    self._send_json({"success": False, "error": "缺少配置数据"}, 400)
                    return
                if db_manager.enabled:
                    db_manager.upsert_config('api_config', config_data, user.get('id') if user else None)
                    self._audit(user, 'api_config_import', 'system_config', 'api_config', {'action': action})
                    self._send_json({
                        "success": True,
                        "message": "配置已导入"
                    })
                    return
                api_config_manager.import_config(config_data)
                self._send_json({
                    "success": True,
                    "message": "配置已导入"
                })

            else:
                self._send_json({"success": False, "error": "未知的action"}, 400)

        except Exception as e:
            log(f"更新API配置失败: {e}")
            self._send_json({"success": False, "error": str(e)}, 500)
