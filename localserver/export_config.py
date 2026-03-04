#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置导出脚本 - 从 localStorage 导出配置到 YAML
"""

import os
import sys
import yaml
import json
from datetime import datetime

# 添加 localserver 到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_config import api_config_manager, API_CONFIG_FILE

def create_default_config():
    """创建默认的 API 配置 (基于前端代码中的 DEFAULT_PROVIDERS)"""
    
    default_base_url = 'https://ai.comfly.chat'
    jimeng_api_base = 'http://localhost:5100'
    
    config = {
        'version': '1.0',
        'updated_at': datetime.now().isoformat(),
        'global_api_key': '',
        'local_server_url': 'http://127.0.0.1:9527',
        'features': {
            'save_assets_zip': False,
            'history_limit': 80,
            'use_local_files': False
        },
        'providers': {
            'openai': {
                'key': '',
                'url': default_base_url,
                'apiType': 'openai',
                'useProxy': False,
                'forceAsync': False,
                'enabled': True
            },
            'google': {
                'key': '',
                'url': default_base_url,
                'apiType': 'openai',
                'useProxy': False,
                'forceAsync': False,
                'enabled': True
            },
            'deepseek': {
                'key': '',
                'url': default_base_url,
                'apiType': 'openai',
                'useProxy': False,
                'forceAsync': False,
                'enabled': True
            },
            'midjourney': {
                'key': '',
                'url': 'https://api.midjourney.com',
                'apiType': 'openai',
                'useProxy': False,
                'forceAsync': False,
                'enabled': True
            },
            'jimeng': {
                'key': '',
                'url': jimeng_api_base,
                'apiType': 'openai',
                'useProxy': False,
                'forceAsync': False,
                'enabled': True
            },
            'grok': {
                'key': '',
                'url': 'https://ai.t8star.cn',
                'apiType': 'openai',
                'useProxy': False,
                'forceAsync': False,
                'enabled': True
            },
            'yunwu': {
                'key': '',
                'url': 'https://yunwu.ai',
                'apiType': 'gemini',
                'useProxy': False,
                'forceAsync': False,
                'enabled': True
            }
        },
        'api_keys': {},
        'model_library': []  # 模型库配置
    }
    
    return config

def export_config():
    """导出配置到 YAML 文件"""
    print("=" * 60)
    print("Tapnow API 配置导出工具")
    print("=" * 60)
    print()
    
    # 加载现有配置（如果有）
    existing = {}
    if os.path.exists(API_CONFIG_FILE):
        print(f"发现现有配置: {API_CONFIG_FILE}")
        try:
            with open(API_CONFIG_FILE, 'r', encoding='utf-8') as f:
                existing = yaml.safe_load(f) or {}
            print("将合并现有配置...")
        except Exception as e:
            print(f"读取现有配置失败: {e}")
    
    # 创建默认配置
    default_config = create_default_config()
    
    # 合并现有配置
    if existing:
        # 保留现有配置的值，但确保结构完整
        for key in ['global_api_key', 'local_server_url']:
            if existing.get(key):
                default_config[key] = existing[key]
        
        # 合并 providers
        if existing.get('providers'):
            for provider_id, provider_config in existing['providers'].items():
                if provider_id in default_config['providers']:
                    default_config['providers'][provider_id].update(provider_config)
                else:
                    default_config['providers'][provider_id] = provider_config
        
        # 合并 features
        if existing.get('features'):
            default_config['features'].update(existing['features'])
        
        # 合并模型库
        if existing.get('model_library'):
            default_config['model_library'] = existing['model_library']
    
    # 确保目录存在
    from api_config import ensure_config_dir
    ensure_config_dir()
    
    # 保存配置（会自动加密 api_keys）
    api_config_manager.save_config(default_config)
    
    print(f"\n✓ 配置已保存到: {API_CONFIG_FILE}")
    print()
    print("配置结构预览:")
    print(f"  - 全局 API Key: {'已设置' if default_config.get('global_api_key') else '未设置'}")
    print(f"  - 本地服务地址: {default_config['local_server_url']}")
    print(f"  - Provider 数量: {len(default_config['providers'])}")
    print(f"  - Features: {list(default_config['features'].keys())}")
    print(f"  - 模型库条目: {len(default_config.get('model_library', []))}")
    print()
    print("=" * 60)
    print("提示：在前端页面控制台运行以下代码导出当前配置：")
    print("-" * 60)
    print('''
// 复制这段代码到浏览器控制台运行
const exportConfig = () => {
    const providers = JSON.parse(localStorage.getItem('tapnow_providers') || '{}');
    const globalKey = localStorage.getItem('tapnow_global_api_key') || '';
    const localUrl = localStorage.getItem('tapnow_local_server_url') || 'http://127.0.0.1:9527';
    const saveZip = localStorage.getItem('tapnow_save_assets_zip') === 'true';
    const historyLimit = parseInt(localStorage.getItem('tapnow_history_limit') || '80');
    const useLocal = localStorage.getItem('tapnow_use_local_files') === 'true';
    const modelLibrary = JSON.parse(localStorage.getItem('tapnow_model_library') || '[]');
    
    const config = {
        global_api_key: globalKey,
        local_server_url: localUrl,
        features: {
            save_assets_zip: saveZip,
            history_limit: historyLimit,
            use_local_files: useLocal
        },
        providers: providers,
        model_library: modelLibrary
    };
    
    // 发送到后端保存
    fetch('http://127.0.0.1:9527/api-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'update', config: config })
    }).then(r => r.json()).then(result => {
        console.log('配置导出结果:', result);
    });
};
exportConfig();
''')
    print("=" * 60)

if __name__ == '__main__':
    export_config()
