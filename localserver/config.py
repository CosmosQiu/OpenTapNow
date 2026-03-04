#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置模块 - 包含所有全局配置、常量、功能开关和状态
"""

import os
import sys
import queue
import uuid
import threading

# ==============================================================================
# SECTION 1: 依赖检查
# ==============================================================================

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[提示] PIL未安装，PNG转JPG功能将不可用 (pip install Pillow)")

try:
    import websocket
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False
    print("[提示] websocket-client未安装，ComfyUI中间件功能将不可用 (pip install websocket-client)")

# ==============================================================================
# SECTION 2: 功能开关 (Feature Flags)
# ==============================================================================

def get_env_bool(key, default):
    val = os.environ.get(key)
    if val is None:
        return default
    return val.lower() in ('true', '1', 'yes', 'on')

FEATURES = {
    # 核心文件服务 (默认开启)
    "file_server": get_env_bool("TAPNOW_ENABLE_FILE_SERVER", True),

    # 代理服务 (默认开启)
    "proxy_server": get_env_bool("TAPNOW_ENABLE_PROXY", True),

    # ComfyUI 中间件 (依赖存在且未被环境变量禁用时开启)
    "comfy_middleware": get_env_bool("TAPNOW_ENABLE_COMFY", WS_AVAILABLE),

    # 控制台日志 (可关闭以减少噪音)
    "log_console": get_env_bool("TAPNOW_ENABLE_LOG", True)
}

# ==============================================================================
# SECTION 3: 默认配置常量
# ==============================================================================

DEFAULT_PORT = 9527
DEFAULT_SAVE_PATH = os.path.expanduser("~/Downloads/TapnowStudio")
DEFAULT_ALLOWED_ROOTS = [
    os.path.expanduser("~/Downloads"),
    os.path.abspath(r"D:\TapnowData")
]
DEFAULT_PROXY_ALLOWED_HOSTS = [
    "api.openai.com", "generativelanguage.googleapis.com",
    "ai.comfly.chat", "api-inference.modelscope.cn",
    "vibecodingapi.ai", "yunwu.ai",
    "muse-ai.oss-cn-hangzhou.aliyuncs.com", "googlecdn.datas.systems",
    "127.0.0.1:8188", "localhost:8188"
]
DEFAULT_PROXY_TIMEOUT = 300
CONFIG_FILENAME = "tapnow-local-config.json"
LOCAL_FILE_CACHE_CONTROL = "public, max-age=31536000, immutable"
PROXY_MEDIA_CACHE_CONTROL = "public, max-age=86400, stale-while-revalidate=604800"
MEDIA_FILE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.avif',
    '.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v'
}

# ComfyUI 特有配置
COMFY_URL = "http://127.0.0.1:8188"
COMFY_WS_URL = "ws://127.0.0.1:8188/ws"
WORKFLOWS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflows")

# ==============================================================================
# SECTION 4: 全局运行时配置字典
# ==============================================================================

config = {
    "port": DEFAULT_PORT,
    "save_path": DEFAULT_SAVE_PATH,
    "static_dir": "",  # 静态文件目录
    "image_save_path": "",
    "video_save_path": "",
    "allowed_roots": DEFAULT_ALLOWED_ROOTS,
    "proxy_allowed_hosts": DEFAULT_PROXY_ALLOWED_HOSTS,
    "proxy_timeout": DEFAULT_PROXY_TIMEOUT,
    "auto_create_dir": True,
    "allow_overwrite": False,
    "log_enabled": True,
    "convert_png_to_jpg": True,
    "jpg_quality": 95
}

# ==============================================================================
# SECTION 5: 全局状态对象 (ComfyUI 队列相关)
# ==============================================================================

JOB_QUEUE = queue.Queue()
JOB_STATUS = {}
STATUS_LOCK = threading.Lock()
CLIENT_ID = str(uuid.uuid4())
WS_MESSAGES = {}
PROMPT_TO_JOB = {}
