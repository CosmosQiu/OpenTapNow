#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComfyUI 中间件模块 - 处理 ComfyUI 相关任务队列和 Workflow 管理
"""

import os
import json
import random
import time
import threading
import urllib.request
import urllib.error

from config import (
    FEATURES, WS_AVAILABLE, CLIENT_ID, COMFY_URL, COMFY_WS_URL, WORKFLOWS_DIR,
    JOB_QUEUE, JOB_STATUS, STATUS_LOCK, WS_MESSAGES, PROMPT_TO_JOB
)
from utils import log, read_json_file
from db import db_manager

try:
    import websocket
except ImportError:
    websocket = None

# ==============================================================================
# ComfyUI 中间件类
# ==============================================================================

class ComfyMiddleware:
    """封装所有 ComfyUI 相关逻辑"""

    @staticmethod
    def coerce_value(val):
        """类型转换"""
        if isinstance(val, str):
            raw = val.strip()
            if raw.lower() in ('true', 'false'):
                return raw.lower() == 'true'
            if raw == '':
                return ''
            try:
                if '.' in raw:
                    return float(raw)
                return int(raw)
            except Exception:
                return val
        return val

    @staticmethod
    def normalize_seed_value(value):
        """处理种子值 (-1 表示随机)"""
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == '-1':
            return random.randint(0, 2**31 - 1)
        if isinstance(value, (int, float)) and int(value) == -1:
            return random.randint(0, 2**31 - 1)
        return value

    @staticmethod
    def set_by_path(target, path_parts, value):
        """通过路径设置值"""
        current = target
        for part in path_parts[:-1]:
            if not isinstance(current, dict):
                return False
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        if isinstance(current, dict):
            current[path_parts[-1]] = value
            return True
        return False

    @staticmethod
    def extract_batch_size(workflow):
        """提取批次大小"""
        try:
            for node in workflow.values():
                if not isinstance(node, dict):
                    continue
                inputs = node.get('inputs')
                if not isinstance(inputs, dict):
                    continue
                if 'batch_size' in inputs:
                    try:
                        return int(inputs.get('batch_size') or 1)
                    except Exception:
                        return 1
        except Exception:
            return 1
        return 1

    @staticmethod
    def is_enabled():
        """检查是否启用"""
        return FEATURES["comfy_middleware"]

    @staticmethod
    def load_template(app_id):
        """读取 Workflow 模板"""
        if db_manager.enabled:
            workflow = db_manager.get_latest_workflow_content(app_id)
            if workflow:
                return workflow, {}
        template_path = os.path.join(WORKFLOWS_DIR, app_id, "template.json")
        meta_path = os.path.join(WORKFLOWS_DIR, app_id, "meta.json")

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"模板不存在: {app_id}")

        workflow = read_json_file(template_path)

        params_map = {}
        if os.path.exists(meta_path):
            meta = read_json_file(meta_path)
            params_map = meta.get('params_map', {})

        return workflow, params_map

    @staticmethod
    def apply_inputs(workflow, params_map, user_inputs):
        """填充参数到 Workflow"""
        if not user_inputs:
            return workflow

        # RunningHub List 格式
        if isinstance(user_inputs, list):
            for item in user_inputs:
                node_id = str(item.get('nodeId') or item.get('node_id') or item.get('id') or '').strip()
                field = (item.get('fieldName') or item.get('field') or '').strip()
                if not node_id or not field:
                    continue
                raw_value = item.get('fieldValue')
                if raw_value is None:
                    continue
                if isinstance(raw_value, str) and raw_value.strip() == '':
                    continue
                value = ComfyMiddleware.coerce_value(raw_value)
                if field == 'seed':
                    value = ComfyMiddleware.normalize_seed_value(value)
                if node_id in workflow:
                    inputs = workflow[node_id].setdefault('inputs', {})
                    if isinstance(inputs, dict):
                        inputs[field] = value
            return workflow

        # 默认 Dict 模式
        if not isinstance(user_inputs, dict):
            return workflow

        def find_unique_node_with_input(input_name):
            matches = []
            for node_id, node in workflow.items():
                inputs = node.get('inputs') if isinstance(node, dict) else None
                if isinstance(inputs, dict) and input_name in inputs:
                    matches.append(node_id)
            return matches

        for key, val in user_inputs.items():
            if val is None:
                continue
            if isinstance(val, str) and val.strip() == '':
                continue
            if isinstance(key, str):
                # 支持前端 *_input 命名
                if key.endswith('_input') and len(key) > 6:
                    key = key[:-6]
                if key in ('batch_size', 'batchSize'):
                    key = 'batch'
                if key in ('sampler_name', 'samplerName'):
                    key = 'sampler'
            value = ComfyMiddleware.coerce_value(val)
            handled = False
            if key in params_map:
                mapping = params_map[key]
                node_id = str(mapping.get('node_id', '')).strip()
                field_path = (mapping.get('field', '') or '').split('.')
                if node_id in workflow and field_path and field_path[0]:
                    if field_path[-1] == 'seed':
                        value = ComfyMiddleware.normalize_seed_value(value)
                    target = workflow[node_id]
                    if not ComfyMiddleware.set_by_path(target, field_path, value):
                        log(f"[Comfy] 参数填充失败 {key}: 无法写入路径 {field_path}")
                handled = True
                continue

            # 兼容 BizyAir 风格: "NodeID:NodeType.field"
            if isinstance(key, str) and ':' in key:
                node_part, field_part = key.split(':', 1)
                node_id = node_part.strip()
                field_name = field_part.split('.')[-1].strip() if field_part else ''
                if node_id in workflow and field_name:
                    if field_name == 'seed':
                        value = ComfyMiddleware.normalize_seed_value(value)
                    inputs = workflow[node_id].setdefault('inputs', {})
                    if isinstance(inputs, dict):
                        inputs[field_name] = value
                handled = True
                continue

            # 兼容简化 "NodeID.field"
            if isinstance(key, str) and '.' in key:
                node_part, field_name = key.split('.', 1)
                node_id = node_part.strip()
                field_name = field_name.strip()
                if node_id in workflow and field_name:
                    if field_name == 'seed':
                        value = ComfyMiddleware.normalize_seed_value(value)
                    inputs = workflow[node_id].setdefault('inputs', {})
                    if isinstance(inputs, dict):
                        inputs[field_name] = value
                handled = True
                continue

            # 兜底：允许用通用键名
            if not handled and isinstance(key, str):
                alias_map = {
                    "prompt": ["text", "prompt"],
                    "text": ["text", "prompt"],
                    "seed": ["seed"],
                    "steps": ["steps"],
                    "width": ["width"],
                    "height": ["height"],
                    "batch": ["batch_size", "batch"],
                    "sampler": ["sampler_name", "sampler"],
                    "scheduler": ["scheduler"]
                }
                if key in alias_map:
                    for input_name in alias_map[key]:
                        matches = find_unique_node_with_input(input_name)
                        if len(matches) == 1:
                            inputs = workflow[matches[0]].setdefault('inputs', {})
                            if isinstance(inputs, dict):
                                if input_name == 'seed':
                                    value = ComfyMiddleware.normalize_seed_value(value)
                                inputs[input_name] = value
                            handled = True
                            break
                if not handled and key in ("seed", "steps", "width", "height"):
                    matches = find_unique_node_with_input(key)
                    if len(matches) == 1:
                        inputs = workflow[matches[0]].setdefault('inputs', {})
                        if isinstance(inputs, dict):
                            if key == 'seed':
                                value = ComfyMiddleware.normalize_seed_value(value)
                            inputs[key] = value
                        handled = True
        return workflow

    @staticmethod
    def send_to_comfy(workflow):
        """提交 Prompt 到 ComfyUI"""
        payload = {"client_id": CLIENT_ID, "prompt": workflow}
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f"{COMFY_URL}/prompt",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                try:
                    return json.loads(raw.decode('utf-8-sig'))
                except Exception:
                    return json.loads(raw)
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode('utf-8', errors='replace')
                log(f"[Comfy] HTTPError {e.code}: {err_body}")
            except Exception:
                log(f"[Comfy] HTTPError {e.code}")
            raise

    @staticmethod
    def worker_loop():
        """后台 Worker 线程的主循环"""
        if not ComfyMiddleware.is_enabled():
            return

        log("ComfyUI Worker 线程已启动 (等待任务...)")

        # 1. 启动 WebSocket 监听线程
        def on_message(ws, message):
            try:
                msg = json.loads(message)
                mtype = msg.get('type')
                if mtype == 'executed':  # 节点执行完成
                    pid = msg.get('data', {}).get('prompt_id')
                    if not pid:
                        return
                    if pid not in WS_MESSAGES:
                        WS_MESSAGES[pid] = []
                    WS_MESSAGES[pid].append(msg)
                elif mtype == 'progress':
                    data = msg.get('data', {})
                    pid = data.get('prompt_id')
                    if not pid:
                        return
                    job_id = PROMPT_TO_JOB.get(pid)
                    if not job_id:
                        return
                    with STATUS_LOCK:
                        if job_id in JOB_STATUS:
                            JOB_STATUS[job_id]['progress'] = {
                                'value': data.get('value', 0),
                                'max': data.get('max', 0)
                            }
                elif mtype == 'execution_error':
                    data = msg.get('data', {})
                    pid = data.get('prompt_id')
                    job_id = PROMPT_TO_JOB.get(pid) if pid else None
                    if job_id:
                        with STATUS_LOCK:
                            if job_id in JOB_STATUS and JOB_STATUS[job_id].get('status') not in ('success', 'failed'):
                                JOB_STATUS[job_id]['status'] = 'failed'
                                JOB_STATUS[job_id]['error'] = data.get('exception_message') or 'execution_error'
            except:
                pass

        def ws_thread_func():
            while True:
                try:
                    # 自动重连逻辑
                    ws = websocket.WebSocketApp(f"{COMFY_WS_URL}?clientId={CLIENT_ID}", on_message=on_message)
                    ws.run_forever()
                except Exception:
                    time.sleep(5)
                time.sleep(1)

        threading.Thread(target=ws_thread_func, daemon=True).start()

        # 2. 任务处理循环
        while True:
            job = JOB_QUEUE.get()  # 阻塞获取任务
            job_id = job['id']
            prompt_id = None

            with STATUS_LOCK:
                JOB_STATUS[job_id]['status'] = 'processing'
                JOB_STATUS[job_id]['started_at'] = time.time()
                JOB_STATUS[job_id]['progress'] = {'value': 0, 'max': 0}

            try:
                log(f"[Comfy] 开始执行任务: {job_id} ({job['app_id']})")

                # 加载与填充
                if job.get('prompt'):
                    wf = job['prompt']
                else:
                    wf, pmap = ComfyMiddleware.load_template(job['app_id'])
                    wf = ComfyMiddleware.apply_inputs(wf, pmap, job['inputs'])

                # 提交
                resp = ComfyMiddleware.send_to_comfy(wf)
                prompt_id = resp['prompt_id']
                log(f"[Comfy] 已提交到后端, PromptID: {prompt_id}")
                with STATUS_LOCK:
                    JOB_STATUS[job_id]['prompt_id'] = prompt_id
                PROMPT_TO_JOB[prompt_id] = job_id
                expected_count = 1
                try:
                    expected_count = max(1, int(ComfyMiddleware.extract_batch_size(wf)))
                except Exception:
                    expected_count = 1

                # 等待结果
                timeout = 600
                start_t = time.time()
                final_images = []

                last_count = 0
                stable_ticks = 0
                while time.time() - start_t < timeout:
                    if prompt_id in WS_MESSAGES:
                        msgs = WS_MESSAGES[prompt_id]
                        for m in msgs:
                            # 提取 output 图片
                            outputs = m['data'].get('output', {}).get('images', [])
                            for img in outputs:
                                url = f"{COMFY_URL}/view?filename={img['filename']}&type={img['type']}&subfolder={img['subfolder']}"
                                final_images.append(url)
                        if len(final_images) >= expected_count:
                            break
                        if len(final_images) == last_count and final_images:
                            stable_ticks += 1
                            if stable_ticks >= 3:
                                break
                        else:
                            stable_ticks = 0
                            last_count = len(final_images)
                    time.sleep(0.5)

                if final_images:
                    with STATUS_LOCK:
                        JOB_STATUS[job_id]['status'] = 'success'
                        JOB_STATUS[job_id]['result'] = {'images': final_images}
                        JOB_STATUS[job_id]['finished_at'] = time.time()
                        JOB_STATUS[job_id]['progress'] = {'value': 100, 'max': 100}
                    log(f"[Comfy] 任务完成: {len(final_images)} images")
                else:
                    raise TimeoutError("等待生成结果超时")

            except Exception as e:
                log(f"[Comfy] 任务异常: {e}")
                with STATUS_LOCK:
                    JOB_STATUS[job_id]['status'] = 'failed'
                    JOB_STATUS[job_id]['error'] = str(e)
                    JOB_STATUS[job_id]['finished_at'] = time.time()
            finally:
                if prompt_id in WS_MESSAGES:
                    WS_MESSAGES.pop(prompt_id, None)
                if prompt_id in PROMPT_TO_JOB:
                    PROMPT_TO_JOB.pop(prompt_id, None)
                JOB_QUEUE.task_done()

# ==============================================================================
# 辅助函数
# ==============================================================================

def format_timestamp(ts):
    """格式化时间戳"""
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""

def normalize_job_status(status):
    """规范化任务状态"""
    mapping = {
        'queued': 'Queued',
        'processing': 'Running',
        'success': 'Success',
        'failed': 'Failed',
        'canceled': 'Canceled'
    }
    if not status:
        return 'Unknown'
    return mapping.get(status, status)

def build_detail_response(job):
    """构建任务详情响应"""
    data = {
        "requestId": job.get('id'),
        "taskId": job.get('id'),
        "app_id": job.get('app_id'),
        "status": normalize_job_status(job.get('status')),
        "created_at": format_timestamp(job.get('created_at', 0)),
        "updated_at": format_timestamp(job.get('finished_at') or job.get('started_at') or job.get('created_at', 0)),
        "progress": job.get('progress') or {"value": 0, "max": 0}
    }
    if job.get('prompt_id'):
        data["prompt_id"] = job.get('prompt_id')
    if job.get('error'):
        data["error"] = job.get('error')
    return {
        "code": 20000,
        "message": "Ok",
        "status": True,
        "data": data
    }

def build_outputs_response(job):
    """构建任务输出响应"""
    outputs = []
    images = job.get('result', {}).get('images', []) if job else []
    for url in images:
        outputs.append({"object_url": url})
    return {
        "code": 20000,
        "message": "Ok",
        "status": True,
        "data": {
            "outputs": outputs,
            "images": images
        },
        "outputs": outputs
    }

def resolve_job_by_request_id(request_id):
    """通过请求ID解析任务"""
    if not request_id:
        return None
    with STATUS_LOCK:
        job = JOB_STATUS.get(request_id)
        if job:
            return job
        for candidate in JOB_STATUS.values():
            if candidate.get('prompt_id') == request_id:
                return candidate
    return None

from datetime import datetime
