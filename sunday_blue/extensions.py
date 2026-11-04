"""Text-only extensions and an opt-in MCP stdio tools client."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from .files import no_links, inside

def extension_text(root, role_config):
    parts = []
    base = Path(root) / 'extensions'
    for name in role_config.get('skills', []):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError('Skill 目录名只支持字母、数字、下划线和短横线。')
        p = base / 'skills' / name / 'SKILL.md'
        no_links(p)
        if not p.is_file() or p.stat().st_size > 65536:
            raise ValueError(f'Skill 不存在或超过 64 KiB: {name}')
        parts.append(f'\n<skill name="{name}">\n{p.read_text(encoding="utf-8-sig")}\n</skill>')
    for name in role_config.get('plugins', []):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError('无效插件 ID')
        p = base / 'plugins' / (name + '.json')
        no_links(p)
        obj = json.loads(p.read_text(encoding='utf-8-sig'))
        prompt=role_config.get('plugin_settings',{}).get(name,{}).get('prompt',obj.get('prompt',''))
        parts.append('\n<plugin>\n' + str(prompt)[:65536] + '\n</plugin>')
    result = '\n'.join(parts)
    if len(result) > 150000:
        raise ValueError('启用的扩展提示词过多，请减少 Skill / 插件。')
    return result

def validate_servers(servers):
    from .storage import ROLE_IDS
    if not isinstance(servers, list):
        raise ValueError('MCP 配置必须是 JSON 数组。')
    names = set()
    for s in servers:
        if not isinstance(s, dict) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', s.get('name', '')):
            raise ValueError('MCP name 必须为 1–40 位字母、数字、短横线或下划线。')
        if s['name'] in names:
            raise ValueError('MCP 名称不能重复。')
        names.add(s['name'])
        if not isinstance(s.get('command'), str) or not s['command'].strip():
            raise ValueError('MCP command 不能为空。')
        if not isinstance(s.get('args', []), list) or not all(isinstance(x, str) for x in s.get('args', [])):
            raise ValueError('MCP args 必须是字符串数组。')
        if not isinstance(s.get('env', {}), dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in s.get('env', {}).items()):
            raise ValueError('MCP env 必须是字符串映射。')
        if not isinstance(s.get('roles', []), list) or not set(s.get('roles', [])) <= ROLE_IDS:
            raise ValueError('MCP roles 必须是有效角色 ID 数组；空数组不授予任何角色。')
        if not isinstance(s.get('enabled', False), bool):
            raise ValueError('MCP enabled 必须为布尔值。')
        if s.get('transport', 'stdio') != 'stdio':
            raise ValueError('当前版本支持本地 stdio MCP，暂不支持远程 HTTP。')
    return servers

class MCPClient:
    def __init__(self, spec, cancel):
        self.spec, self.cancel = spec, cancel
        self.messages = queue.Queue()
        self.counter = 0
        env = {k:v for k,v in os.environ.items() if k.upper() in {
            'SYSTEMROOT', 'WINDIR', 'PATH', 'PATHEXT', 'TEMP', 'TMP', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'COMSPEC'}}
        env.update(spec.get('env', {}))
        self.process = subprocess.Popen([spec['command'], *spec.get('args', [])],
            cwd=spec.get('cwd') or None, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.call('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {},
                      'clientInfo': {'name': 'Sunday Blue', 'version': '0.1.0'}})
            self.send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        except Exception:
            self.close()
            raise

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(2 * 1024 * 1024 + 1)
                if not line:
                    break
                if len(line) > 2 * 1024 * 1024:
                    self.messages.put(RuntimeError('MCP 单条消息超过 2 MiB。'))
                    return
                try:
                    self.messages.put(json.loads(line))
                except ValueError:
                    self.messages.put(RuntimeError('MCP stdout 必须只包含 JSON-RPC 消息。'))
                    return
        finally:
            self.messages.put(None)

    def send(self, obj):
        self.process.stdin.write(json.dumps(obj, ensure_ascii=False) + '\n')
        self.process.stdin.flush()

    def call(self, method, params, timeout=45):
        self.counter += 1
        rid = self.counter
        self.send({'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params})
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.cancel.is_set():
                from .provider import Cancelled
                raise Cancelled()
            try:
                value = self.messages.get(timeout=.2)
            except queue.Empty:
                continue
            if value is None:
                raise RuntimeError('MCP 进程已退出。')
            if isinstance(value, Exception):
                raise value
            if 'method' in value and 'id' in value:
                if value['method'] == 'ping':
                    self.send({'jsonrpc': '2.0', 'id': value['id'], 'result': {}})
                else:
                    self.send({'jsonrpc': '2.0', 'id': value['id'], 'error': {'code': -32601, 'message': 'Not supported'}})
            elif value.get('id') == rid:
                if 'error' in value:
                    raise RuntimeError('MCP 调用失败：' + str(value['error'].get('code', 'unknown')))
                return value.get('result', {})
        raise TimeoutError('MCP 超时；操作结果可能未知，请先核实，勿盲目重试。')

    def tools(self):
        result, cursor = [], None
        for _ in range(10):
            page = self.call('tools/list', {'cursor': cursor} if cursor else {})
            result.extend(page.get('tools', []))
            cursor = page.get('nextCursor')
            if not cursor:
                return result
        raise ValueError('MCP 工具列表分页过多。')

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
        for pipe in (self.process.stdin, self.process.stdout):
            if pipe:
                pipe.close()
