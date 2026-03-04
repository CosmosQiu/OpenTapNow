#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tapnow-online 服务器主入口

版本: 2.3 (ComfyUI Compatible)

功能概述:
1. [Core] 本地文件服务: 提供文件的保存 (/save)、批量操作、删除等基础能力。
2. [Core] HTTP 代理服务: 绕过浏览器 CORS 限制 (/proxy)。
3. [Module] ComfyUI 中间件: 任务队列、模板管理、BizyAir/RunningHub 风格接口 (/comfy/*)。
"""

import os
import sys
import argparse
import threading
from http.server import ThreadingHTTPServer

# 导入各模块
from config import config, FEATURES, DEFAULT_PORT, WORKFLOWS_DIR
from utils import log, ensure_dir, load_config_file
from handlers import TapnowFullHandler
from comfy_middleware import ComfyMiddleware
from db import db_manager

# ==============================================================================
# 主程序入口
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description='Tapnow Studio Local Server v2.3')
    parser.add_argument('-p', '--port', type=int, default=DEFAULT_PORT, help='Port number')
    parser.add_argument('-d', '--dir', type=str, default=config["save_path"], help='Save directory')
    parser.add_argument('--static-dir', type=str, default='', help='Static files directory for web frontend')
    args = parser.parse_args()

    # 1. 初始化配置
    config["port"] = args.port
    config["save_path"] = os.path.abspath(os.path.expanduser(args.dir))
    if args.static_dir:
        config["static_dir"] = os.path.abspath(os.path.expanduser(args.static_dir))
    # 也支持从环境变量读取
    elif os.environ.get('TAPNOW_STATIC_DIR'):
        config["static_dir"] = os.path.abspath(os.path.expanduser(os.environ.get('TAPNOW_STATIC_DIR')))
    load_config_file()

    # 1.1 初始化数据库（可通过 DATABASE_URL / TAPNOW_DATABASE_URL 启用）
    try:
        db_manager.init()
        if db_manager.enabled:
            log("数据库已连接，启用 MySQL 持久化模式")
        else:
            log("未配置数据库连接串，使用文件系统兼容模式")
    except Exception as exc:
        log(f"数据库初始化失败，将继续以文件系统模式运行: {exc}")

    # 2. 准备目录
    ensure_dir(config["save_path"])
    if FEATURES["comfy_middleware"]:
        ensure_dir(WORKFLOWS_DIR)

    # 3. 启动后台线程
    if FEATURES["comfy_middleware"]:
        t = threading.Thread(target=ComfyMiddleware.worker_loop, daemon=True)
        t.start()
        log(f"ComfyUI 中间件模块已启用 (Workflows: {WORKFLOWS_DIR})")
    else:
        log("ComfyUI 中间件模块已禁用 (缺少 websocket-client 或手动关闭)")

    # 4. 启动 HTTP 服务
    server = ThreadingHTTPServer(('0.0.0.0', args.port), TapnowFullHandler)

    print("=" * 60)
    print(f"  Tapnow Local Server v2.3 running on http://0.0.0.0:{args.port}")
    print(f"  Save Path: {config['save_path']}")
    if config["static_dir"]:
        print(f"  Static Dir: {config['static_dir']}")
    print("-" * 60)
    print("  Modules:")
    print(f"  [x] File Server")
    print(f"  [x] HTTP Proxy")
    if config["static_dir"]:
        print(f"  [x] Static Web Server")
    print(f"  [{'x' if FEATURES['comfy_middleware'] else ' '}] ComfyUI Middleware")
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")

if __name__ == '__main__':
    main()
