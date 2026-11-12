"""Two wire adapters; a single Anthropic-shaped internal transcript."""
from __future__ import annotations
import json
import threading
from urllib.parse import urlsplit
import requests
from .storage import protect

_COUNT_UNSUPPORTED=set()

class Cancelled(Exception):
    pass

def endpoint(base, protocol):
    base = base.strip().rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('请求地址必须为 http(s) URL；请将密钥单独填入 API Key。')
    suffix = '/messages' if protocol == 'anthropic' else '/chat/completions'
    if base.endswith(suffix):
        return base
    return base + ('' if parsed.path.rstrip('/').endswith('/v1') else '/v1') + suffix

def openai_messages(system, messages):
    out = [{'role': 'system', 'content': system}]
    for m in messages:
        content = m['content']
        if isinstance(content, str):
            out.append({'role': m['role'], 'content': content})
            continue
        text = '\n'.join(x.get('text', '') for x in content if x['type'] == 'text')
        calls = [{'id': x['id'], 'type': 'function', 'function': {'name': x['name'], 'arguments': json.dumps(x['input'], ensure_ascii=False)}}
                 for x in content if x['type'] == 'tool_use']
        results = [x for x in content if x['type'] == 'tool_result']
        if text or calls:
            row = {'role': m['role'], 'content': text or None}
            if calls:
                row['tool_calls'] = calls
            out.append(row)
        for x in results:
            out.append({'role': 'tool', 'tool_call_id': x['tool_use_id'], 'content': x['content']})
    return out

class Provider:
    def __init__(self, config, cancel=None):
        self.config = config
        self.cancel = cancel or threading.Event()
        self.response = None

    def count_tokens(self,system,messages,tools=None):
        if not self.config.get('model'):return None
        counter_key=(self.config.get('base_url'),self.config.get('model'))
        if self.config['protocol']!='anthropic' or counter_key in _COUNT_UNSUPPORTED:return None
        c=self.config;key=protect(c.get('key_encrypted',''),decrypt=True)
        headers={'anthropic-version':'2023-06-01','Content-Type':'application/json'}
        headers['Authorization' if c.get('auth')=='bearer' else 'x-api-key']=('Bearer '+key) if c.get('auth')=='bearer' else key
        body={'model':c['model'],'system':system,'messages':[{'role':m['role'],'content':m['content']} for m in messages]}
        if tools:body['tools']=tools
        try:
            with requests.post(endpoint(c['base_url'],'anthropic')+'/count_tokens',headers=headers,json=body,timeout=(5,20),allow_redirects=False) as response:
                if response.status_code!=200:
                    if response.status_code in (404,405,501):_COUNT_UNSUPPORTED.add(counter_key)
                    return None
                count=response.json().get('input_tokens')
                if count is None:_COUNT_UNSUPPORTED.add(counter_key)
                return count if isinstance(count,int) and count>=0 else None
        except (requests.RequestException,ValueError):return None

    def complete(self, system, messages, tools=None, on_text=lambda x: None, max_tokens=None):
        if self.cancel.is_set():
            raise Cancelled()
        c = self.config
        if not c.get('model', '').strip():
            raise ValueError('请在右上角设置中填写模型 ID。')
        key = protect(c.get('key_encrypted', ''), decrypt=True)
        protocol = c['protocol']
        headers = {'Content-Type': 'application/json'}
        if key:
            if protocol == 'anthropic' and c.get('auth', 'x-api-key') == 'x-api-key':
                headers['x-api-key'] = key
            else:
                headers['Authorization'] = 'Bearer ' + key
        stream = c.get('stream', True)
        body = {'model': c['model'], 'max_tokens': max_tokens or c['max_tokens'], 'stream': stream}
        if protocol == 'anthropic':
            headers['anthropic-version'] = '2023-06-01'
            body.update(system=system, messages=[{'role': m['role'], 'content': m['content']} for m in messages])
            if tools:
                body['tools'] = tools
            thinking_budget = int(c.get('thinking_budget') or 0)
            # Only request extended thinking when the model actually has room for it;
            # otherwise the API rejects the request (max_tokens must exceed the budget).
            if thinking_budget > 0 and body['max_tokens'] > thinking_budget:
                body['thinking'] = {'type': 'enabled', 'budget_tokens': thinking_budget}
        else:
            body['messages'] = openai_messages(system, messages)
            if c.get('reasoning_effort'):
                if c.get('reasoning_support') != 'openai_effort':
                    raise ValueError('此连接未声明支持 reasoning_effort；请先在角色模型设置中确认服务商支持。')
                body['reasoning_effort'] = c['reasoning_effort']
            if tools:
                body['tools'] = [{'type': 'function', 'function': {'name': t['name'], 'description': t['description'], 'parameters': t['input_schema']}} for t in tools]
            if stream:
                body['stream_options'] = {'include_usage': True}
        try:
            with requests.post(endpoint(c['base_url'], protocol), headers=headers, json=body,
                               stream=stream, timeout=c.get("request_timeout", (15, 60)), allow_redirects=False) as response:
                self.response = response
                if response.status_code >= 300:
                    # Gateway error bodies can contain request credentials; omit them.
                    raise RuntimeError(f'API 返回 HTTP {response.status_code}。请检查地址、鉴权方式、模型和额度。')
                if not stream:
                    payload = response.json()
                    if protocol == 'anthropic':
                        result = (payload['content'], payload.get('usage', {}), payload.get('stop_reason', ''))
                    else:
                        msg = payload['choices'][0]['message']
                        blocks = [{'type': 'text', 'text': msg.get('content') or ''}]
                        reasoning = msg.get('reasoning') or msg.get('reasoning_content') or ''
                        if reasoning:
                            blocks.insert(0, {'type': 'thinking', 'thinking': reasoning, 'signature': ''})
                        for call in msg.get('tool_calls', []):
                            blocks.append({'type': 'tool_use', 'id': call['id'], 'name': call['function']['name'], 'input': json.loads(call['function']['arguments'])})
                        result = (blocks, payload.get('usage', {}), payload['choices'][0].get('finish_reason', ''))
                    for b in result[0]:
                        if b['type'] == 'text':
                            on_text(b['text'])
                    return result
                return self._stream(response, protocol, on_text)
        except requests.RequestException as exc:
            if self.cancel.is_set():
                raise Cancelled() from None
            raise RuntimeError('网络请求失败或超时：' + type(exc).__name__ + '。可在设置中检查请求地址。') from None
        finally:
            self.response = None

    def _stream(self, response, protocol, on_text):
        blocks, args, usage, finish = {}, {}, {}, ''
        seen_end = False
        for line in response.iter_lines(chunk_size=128):
            if self.cancel.is_set():
                raise Cancelled()
            if not line.startswith(b'data:'):
                continue
            data = line[5:].strip()
            if data == b'[DONE]':
                seen_end = True
                break
            if not data:
                continue
            event = json.loads(data)
            if 'error' in event or event.get('type') == 'error':
                raise RuntimeError('服务端报告流式响应错误，请稍后重试。')
            if protocol == 'anthropic':
                kind = event.get('type')
                index = event.get('index', 0)
                if kind == 'message_start':
                    usage.update(event['message'].get('usage', {}))
                elif kind == 'content_block_start':
                    b = event['content_block']
                    if b['type'] in ('text', 'tool_use', 'thinking', 'redacted_thinking'):
                        blocks[index] = b
                        if b['type'] == 'text' and b.get('text'):
                            on_text(b['text'])
                elif kind == 'content_block_delta':
                    delta = event['delta']
                    if delta['type'] == 'text_delta':
                        blocks.setdefault(index, {'type': 'text', 'text': ''})['text'] += delta['text']
                        on_text(delta['text'])
                    elif delta['type'] == 'thinking_delta':
                        blocks.setdefault(index, {'type': 'thinking', 'thinking': ''})['thinking'] += delta['thinking']
                    elif delta['type'] == 'signature_delta':
                        blocks.setdefault(index, {'type': 'thinking'})['signature'] = delta.get('signature', '')
                    elif delta['type'] == 'input_json_delta':
                        args[index] = args.get(index, '') + delta['partial_json']
                elif kind == 'message_delta':
                    usage.update(event.get('usage', {}))
                    finish = event.get('delta', {}).get('stop_reason') or finish
                elif kind == 'message_stop':
                    seen_end = True
                    break
            else:
                if event.get('usage'):
                    usage.update(event['usage'])
                for choice in event.get('choices', []):
                    if choice.get('finish_reason'):
                        finish = choice['finish_reason']
                    delta = choice.get('delta', {})
                    if delta.get('content'):
                        blocks.setdefault(-1, {'type': 'text', 'text': ''})['text'] += delta['content']
                        on_text(delta['content'])
                    for call in delta.get('tool_calls', []):
                        idx = call['index']
                        b = blocks.setdefault(idx, {'type': 'tool_use', 'id': '', 'name': '', 'input': {}})
                        b['id'] += call.get('id', '')
                        b['name'] += call.get('function', {}).get('name', '')
                        args[idx] = args.get(idx, '') + call.get('function', {}).get('arguments', '')
        if not seen_end:
            raise RuntimeError('流式连接提前结束，未收到完整响应。部分输出未作为完成消息保存。')
        for idx, raw in args.items():
            if raw:
                blocks[idx]['input'] = json.loads(raw)
        return [blocks[i] for i in sorted(blocks)], usage, finish
