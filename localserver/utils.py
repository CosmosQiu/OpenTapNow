#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具函数模块 - 包含日志、文件操作、路径处理、代理工具、图像处理等
"""

import os
import sys
import json
import base64
import mimetypes
import urllib.request
from urllib.parse import unquote, urlparse, parse_qs
from datetime import datetime
from io import BytesIO
from email.utils import formatdate

from config import (
    config, FEATURES, PIL_AVAILABLE,
    DEFAULT_ALLOWED_ROOTS, DEFAULT_PROXY_TIMEOUT,
    LOCAL_FILE_CACHE_CONTROL, PROXY_MEDIA_CACHE_CONTROL,
    MEDIA_FILE_EXTENSIONS, CONFIG_FILENAME
)

# ==============================================================================
# SECTION 1: 日志和文件操作
# ==============================================================================

LOG_MODE_RANK = {
    'error': 0,
    'normal': 1,
    'debug': 2,
}

SENSITIVE_HEADER_KEYS = {
    'authorization', 'proxy-authorization', 'cookie', 'set-cookie',
    'x-api-key', 'api-key', 'x-auth-token'
}


def get_log_mode():
    mode = str(config.get('log_mode', 'normal') or 'normal').strip().lower()
    return mode if mode in LOG_MODE_RANK else 'normal'


def should_log(level='normal'):
    current_rank = LOG_MODE_RANK.get(get_log_mode(), 1)
    required_rank = LOG_MODE_RANK.get(str(level or 'normal').strip().lower(), 1)
    return current_rank >= required_rank


def log(message, level='normal'):
    """统一日志输出（支持 debug/normal/error 分级）"""
    if not (config.get("log_enabled", True) and FEATURES.get("log_console", True)):
        return
    if not should_log(level):
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def log_debug(message):
    log(message, level='debug')


def log_info(message):
    log(message, level='normal')


def log_error(message):
    log(message, level='error')


def redact_sensitive_headers(headers):
    if not isinstance(headers, dict):
        return {}
    redacted = {}
    for key, value in headers.items():
        key_text = str(key)
        if key_text.strip().lower() in SENSITIVE_HEADER_KEYS:
            redacted[key_text] = '***'
        else:
            redacted[key_text] = value
    return redacted


def preview_payload(value, max_kb=8):
    """返回用于日志展示的 payload 摘要，默认最多 8KB。"""
    limit = max(1, int(max_kb or 8)) * 1024
    if value is None:
        return ''
    if isinstance(value, bytes):
        text = value[:limit].decode('utf-8', errors='replace')
        suffix = ' ...<truncated>' if len(value) > limit else ''
        return text + suffix
    if isinstance(value, (dict, list, tuple)):
        try:
            text = json.dumps(value, ensure_ascii=False)
        except Exception:
            text = str(value)
    else:
        text = str(value)
    if len(text.encode('utf-8', errors='replace')) <= limit:
        return text
    encoded = text.encode('utf-8', errors='replace')
    return encoded[:limit].decode('utf-8', errors='replace') + ' ...<truncated>'

def ensure_dir(path):
    """确保目录存在"""
    if not os.path.exists(path):
        try:
            os.makedirs(path)
            log(f"创建目录: {path}")
        except Exception as e:
            log(f"创建目录失败 {path}: {e}")

def load_config_file():
    """加载本地配置文件 (tapnow-local-config.json)"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)
    if not os.path.exists(config_path):
        return
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 安全更新配置，不覆盖未定义的字段
        if data.get("allowed_roots"):
            config["allowed_roots"] = data["allowed_roots"]
        if data.get("proxy_allowed_hosts"):
            config["proxy_allowed_hosts"] = data["proxy_allowed_hosts"]
        if data.get("proxy_timeout"):
            config["proxy_timeout"] = int(data["proxy_timeout"])

        # [NEW] 允许通过 config 文件覆盖环境变量开关
        if "features" in data and isinstance(data["features"], dict):
            for k, v in data["features"].items():
                if k in FEATURES:
                    FEATURES[k] = bool(v)
                    log(f"功能开关已更新 (from config): {k} -> {v}")

        log(f"已加载配置文件: {config_path}")
    except Exception as exc:
        log(f"[警告] 读取配置文件失败: {exc}")

def get_allowed_roots():
    """获取允许的文件操作根目录列表"""
    if sys.platform == 'win32':
        return config.get("allowed_roots", DEFAULT_ALLOWED_ROOTS)
    return [config["save_path"]]

def is_path_allowed(path):
    """安全检查：路径是否在白名单内"""
    try:
        path_abs = os.path.abspath(os.path.expanduser(path))
        path_norm = os.path.normcase(path_abs)
        for root in get_allowed_roots():
            root_abs = os.path.abspath(os.path.expanduser(root))
            root_norm = os.path.normcase(root_abs)
            # 检查 commonpath 前缀是否匹配
            if os.path.commonpath([path_norm, root_norm]) == root_norm:
                return True
    except Exception:
        pass
    return False

def normalize_rel_path(rel_path):
    """规范化相对路径"""
    rel_path = unquote(rel_path or "")
    rel_path = rel_path.replace('\\', '/').lstrip('/')
    if not rel_path:
        return ""
    norm = os.path.normpath(rel_path)
    if norm.startswith("..") or os.path.isabs(norm):
        return None
    return norm.replace('/', os.sep)

def safe_join(base, rel_path):
    """安全地拼接路径"""
    rel_norm = normalize_rel_path(rel_path)
    if rel_norm is None:
        return None
    base_abs = os.path.abspath(base)
    candidate = os.path.abspath(os.path.join(base_abs, rel_norm))
    base_norm = os.path.normcase(base_abs)
    cand_norm = os.path.normcase(candidate)
    try:
        if os.path.commonpath([cand_norm, base_norm]) != base_norm:
            return None
    except ValueError:
        return None
    return candidate

def get_unique_filename(filepath):
    """生成不冲突的文件名 (file.png -> file_1.png)"""
    if not os.path.exists(filepath):
        return filepath
    base, ext = os.path.splitext(filepath)
    counter = 1
    while os.path.exists(f"{base}_{counter}{ext}"):
        counter += 1
    return f"{base}_{counter}{ext}"

# ==============================================================================
# SECTION 2: 代理相关工具
# ==============================================================================

PROXY_SKIP_REQUEST_HEADERS = {
    'host', 'content-length', 'connection', 'proxy-connection', 'keep-alive',
    'transfer-encoding', 'te', 'trailer', 'upgrade', 'proxy-authorization',
    'proxy-authenticate', 'x-proxy-target', 'x-proxy-method'
}
PROXY_SKIP_RESPONSE_HEADERS = {
    'connection', 'proxy-connection', 'keep-alive', 'transfer-encoding', 'te',
    'trailer', 'upgrade', 'proxy-authenticate', 'proxy-authorization',
    'access-control-allow-origin', 'access-control-allow-methods',
    'access-control-allow-headers', 'access-control-expose-headers'
}

def parse_proxy_target(parsed, headers):
    """解析代理目标 URL"""
    target = headers.get('X-Proxy-Target')
    if not target:
        params = parse_qs(parsed.query or '')
        target = params.get('url', [None])[0] or params.get('target', [None])[0]
    return unquote(target) if target else None

def parse_allowed_host_entry(entry):
    """解析允许的host条目"""
    entry = entry.strip()
    if not entry:
        return None, None, False
    if entry == '*':
        return '*', None, False
    wildcard = False
    if entry.startswith('*.'):
        wildcard = True
        entry = entry[2:]
    if '://' in entry:
        parsed = urlparse(entry)
    else:
        parsed = urlparse('//' + entry)
    host = parsed.hostname.lower() if parsed.hostname else None
    return host, parsed.port, wildcard

def is_proxy_target_allowed(target_url):
    """检查代理目标是否被允许"""
    allowed_hosts = config.get("proxy_allowed_hosts", [])
    parsed = urlparse(target_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    # Always allow local ComfyUI output fetch (avoid 403 loop)
    if host in ('127.0.0.1', 'localhost') and port == 8188:
        return True
    if not allowed_hosts:
        return False
    for entry in allowed_hosts:
        if entry is None:
            continue
        host_entry, port_entry, wildcard = parse_allowed_host_entry(str(entry))
        if not host_entry:
            continue
        if host_entry == '*':
            return True
        if wildcard:
            if host == host_entry:
                continue
            if host.endswith('.' + host_entry):
                if port_entry is None or port_entry == port:
                    return True
        else:
            if host == host_entry and (port_entry is None or port_entry == port):
                return True
    return False

def iter_proxy_response_chunks(response, chunk_size=8192):
    """迭代读取代理响应块"""
    if response.fp and hasattr(response.fp, 'read1'):
        while True:
            chunk = response.fp.read1(chunk_size)
            if not chunk:
                break
            yield chunk
        return
    while True:
        chunk = response.read(chunk_size)
        if not chunk:
            break
        yield chunk

# ==============================================================================
# SECTION 3: 图像和文件处理
# ==============================================================================

def convert_png_to_jpg(png_data, quality=95):
    """将 PNG 转换为 JPG"""
    if not PIL_AVAILABLE:
        return png_data, False
    try:
        from PIL import Image
        img = Image.open(BytesIO(png_data))
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        output = BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        return output.getvalue(), True
    except Exception as e:
        log(f"PNG转JPG失败: {str(e)}")
        return png_data, False

def is_image_file(filename):
    """检查是否为图像文件"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']

def is_video_file(filename):
    """检查是否为视频文件"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ['.mp4', '.mov', '.webm', '.avi', '.mkv']

def is_media_content_type(content_type):
    """检查是否为媒体内容类型"""
    if not content_type:
        return False
    lower = content_type.lower()
    return lower.startswith('image/') or lower.startswith('video/') or lower.startswith('audio/')

def is_media_path(path):
    """检查路径是否为媒体文件"""
    try:
        clean_path = (path or '').split('?', 1)[0]
        ext = os.path.splitext(clean_path)[1].lower()
    except Exception:
        return False
    return ext in MEDIA_FILE_EXTENSIONS

def read_json_file(path):
    """读取 JSON 文件"""
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
