#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API配置管理模块 - YAML配置持久化与API Key安全存储
"""

import os
import json
import sqlite3
import yaml
import base64
import hashlib
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from db import db_manager

# 配置文件路径
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config')
API_CONFIG_FILE = os.path.join(CONFIG_DIR, 'api_settings.yaml')
SECRET_KEY_FILE = os.path.join(CONFIG_DIR, '.secret_key')
LOCAL_CONFIG_DB_FILE = os.path.join(CONFIG_DIR, 'tapnow-config.db')
API_CONFIG_DB_KEY = 'api_config'

# 确保配置目录存在
def ensure_config_dir():
    """确保配置目录存在"""
    Path(CONFIG_DIR).mkdir(parents=True, exist_ok=True)

def get_or_create_secret_key() -> bytes:
    """获取或创建加密密钥 (基于机器标识或随机生成)"""
    ensure_config_dir()
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, 'rb') as f:
            return base64.urlsafe_b64decode(f.read().strip())
    
    # 生成新的密钥 (使用机器标识+随机数)
    machine_id = str(uuid.getnode())  # MAC地址
    random_part = os.urandom(16)
    key = hashlib.sha256(machine_id.encode() + random_part).digest()[:32]
    
    # 保存密钥
    with open(SECRET_KEY_FILE, 'wb') as f:
        f.write(base64.urlsafe_b64encode(key))
    
    return key

# 简单的XOR加密 (足够安全用于本地存储)
def xor_encrypt(data: str, key: bytes) -> str:
    """XOR加密字符串"""
    data_bytes = data.encode('utf-8')
    encrypted = bytearray()
    for i, b in enumerate(data_bytes):
        encrypted.append(b ^ key[i % len(key)])
    return base64.urlsafe_b64encode(bytes(encrypted)).decode('ascii')

def xor_decrypt(encrypted_data: str, key: bytes) -> str:
    """XOR解密字符串"""
    try:
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data)
        decrypted = bytearray()
        for i, b in enumerate(encrypted_bytes):
            decrypted.append(b ^ key[i % len(key)])
        return bytes(decrypted).decode('utf-8')
    except Exception:
        return ""

class APIConfigManager:
    """API配置管理器"""
    
    def __init__(self):
        self.secret_key = get_or_create_secret_key()
        self._ensure_config()

    def _can_use_primary_db(self) -> bool:
        return bool(getattr(db_manager, 'enabled', False) and getattr(db_manager, 'engine', None))

    def _sqlite_conn(self):
        ensure_config_dir()
        return sqlite3.connect(LOCAL_CONFIG_DB_FILE)

    def _ensure_local_db(self):
        with self._sqlite_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_configs (
                    config_key TEXT PRIMARY KEY,
                    config_value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
    
    def _ensure_config(self):
        """确保配置存储存在（数据库优先），并兼容迁移旧 YAML 配置"""
        if self._can_use_primary_db():
            existing = db_manager.get_config(API_CONFIG_DB_KEY)
            if existing is None:
                default_config = self._get_default_config()
                legacy = self._load_legacy_yaml_config()
                if legacy:
                    default_config.update(legacy)
                db_manager.upsert_config(API_CONFIG_DB_KEY, default_config, user_id=None)
            return

        self._ensure_local_db()
        existing = self._get_local_config_payload()
        if existing is None:
            default_config = self._get_default_config()
            legacy = self._load_legacy_yaml_config()
            if legacy:
                default_config.update(legacy)
            self._save_local_config_payload(default_config)

    def _load_legacy_yaml_config(self) -> Optional[Dict[str, Any]]:
        if not os.path.exists(API_CONFIG_FILE):
            return None
        try:
            with open(API_CONFIG_FILE, 'r', encoding='utf-8') as f:
                legacy = yaml.safe_load(f) or {}
            if not isinstance(legacy, dict):
                return None
            if 'api_keys' in legacy:
                legacy['api_keys'] = self._decrypt_api_keys(legacy.get('api_keys') or {})
            if legacy.get('global_api_key'):
                legacy['global_api_key'] = xor_decrypt(legacy['global_api_key'], self.secret_key)
            return legacy
        except Exception as e:
            print(f"[API Config] 读取旧 YAML 配置失败: {e}")
            return None

    def _get_local_config_payload(self) -> Optional[Dict[str, Any]]:
        with self._sqlite_conn() as conn:
            row = conn.execute(
                "SELECT config_value_json FROM system_configs WHERE config_key=?",
                (API_CONFIG_DB_KEY,)
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[0] or '{}')
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _save_local_config_payload(self, payload: Dict[str, Any]):
        content = json.dumps(payload or {}, ensure_ascii=False)
        now = datetime.now().isoformat()
        with self._sqlite_conn() as conn:
            conn.execute(
                """
                INSERT INTO system_configs(config_key, config_value_json, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(config_key) DO UPDATE SET
                    config_value_json=excluded.config_value_json,
                    updated_at=excluded.updated_at
                """,
                (API_CONFIG_DB_KEY, content, now)
            )
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置（数据库）"""
        try:
            if self._can_use_primary_db():
                config = db_manager.get_config(API_CONFIG_DB_KEY) or self._get_default_config()
            else:
                config = self._get_local_config_payload() or self._get_default_config()
            
            # 解密API Keys
            if 'api_keys' in config:
                config['api_keys'] = self._decrypt_api_keys(config['api_keys'])
            
            # 解密全局API Key
            if config.get('global_api_key'):
                config['global_api_key'] = xor_decrypt(config['global_api_key'], self.secret_key)
            
            return config
        except Exception as e:
            print(f"[API Config] 加载配置失败: {e}")
            return self._get_default_config()
    
    def save_config(self, config: Dict[str, Any]):
        """保存配置到数据库 (自动加密敏感字段)"""
        config_to_save = config.copy()
        
        # 加密API Keys
        if 'api_keys' in config_to_save:
            config_to_save['api_keys'] = self._encrypt_api_keys(config_to_save['api_keys'])
        
        # 加密全局API Key
        if config_to_save.get('global_api_key'):
            config_to_save['global_api_key'] = xor_encrypt(config_to_save['global_api_key'], self.secret_key)
        
        # 更新修改时间
        config_to_save['updated_at'] = datetime.now().isoformat()
        
        if self._can_use_primary_db():
            db_manager.upsert_config(API_CONFIG_DB_KEY, config_to_save, user_id=None)
            return

        self._save_local_config_payload(config_to_save)
    
    def _encrypt_api_keys(self, api_keys: Dict[str, str]) -> Dict[str, str]:
        """加密所有API Keys"""
        encrypted = {}
        for provider, key in api_keys.items():
            if key:
                encrypted[provider] = xor_encrypt(key, self.secret_key)
        return encrypted
    
    def _decrypt_api_keys(self, api_keys: Dict[str, str]) -> Dict[str, str]:
        """解密所有API Keys"""
        decrypted = {}
        for provider, encrypted_key in api_keys.items():
            if encrypted_key:
                decrypted[provider] = xor_decrypt(encrypted_key, self.secret_key)
        return decrypted
    
    def get_provider_api_key(self, provider_id: str) -> Optional[str]:
        """获取指定provider的API Key"""
        config = self.load_config()
        api_keys = config.get('api_keys', {})
        return api_keys.get(provider_id)
    
    def set_provider_api_key(self, provider_id: str, api_key: str):
        """设置指定provider的API Key"""
        config = self.load_config()
        if 'api_keys' not in config:
            config['api_keys'] = {}
        config['api_keys'][provider_id] = api_key
        self.save_config(config)
    
    def get_provider_config(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """获取Provider配置"""
        config = self.load_config()
        return config.get('providers', {}).get(provider_id)
    
    def set_provider_config(self, provider_id: str, provider_config: Dict[str, Any]):
        """设置Provider配置"""
        config = self.load_config()
        if 'providers' not in config:
            config['providers'] = {}
        config['providers'][provider_id] = provider_config
        self.save_config(config)
    
    def delete_provider(self, provider_id: str):
        """删除Provider配置"""
        config = self.load_config()
        if 'providers' in config and provider_id in config['providers']:
            del config['providers'][provider_id]
        if 'api_keys' in config and provider_id in config['api_keys']:
            del config['api_keys'][provider_id]
        self.save_config(config)
    
    def update_global_api_key(self, api_key: str):
        """更新全局API Key"""
        config = self.load_config()
        config['global_api_key'] = api_key
        self.save_config(config)
    
    def update_features(self, features: Dict[str, Any]):
        """更新功能开关"""
        config = self.load_config()
        config['features'] = features
        self.save_config(config)
    
    def export_config(self, include_keys: bool = True) -> Dict[str, Any]:
        """导出配置 (用于备份)"""
        config = self.load_config()
        if not include_keys:
            config.pop('api_keys', None)
            config.pop('global_api_key', None)
        return config
    
    def import_config(self, config: Dict[str, Any]):
        """导入配置 (用于恢复)"""
        self.save_config(config)
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'version': '1.0',
            'updated_at': datetime.now().isoformat(),
            'global_api_key': '',
            'local_server_url': 'http://127.0.0.1:9527',
            'features': {
                'save_assets_zip': False,
                'history_limit': 80,
                'use_local_files': False
            },
            'providers': {},
            'api_keys': {},
            'model_library': []
        }

# 全局配置管理器实例
api_config_manager = APIConfigManager()
