"""Provider adapters; credentials stay in the host's DPAPI-protected settings."""
import asyncio
import math
from types import SimpleNamespace
import requests
from astrbot.core.provider.provider import Provider, EmbeddingProvider
from sunday_blue.provider import Provider as HostProvider
from sunday_blue.storage import Config, plain
from sunday_blue.models import RoleProvider


class ChatProvider(Provider):
    provider_config = {'id': 'sunday-chat'}

    def __init__(self, root, role='rui'):
        self.root, self.role = root, role

    async def text_chat(self, prompt, system_prompt='', **kwargs):
        config = Config(self.root).snapshot()
        result, _, finish = await asyncio.to_thread(
            RoleProvider(self.root,self.role,config,purpose='memory').complete, system_prompt,
            [{'role': 'user', 'content': prompt}])
        if finish in ('length', 'max_tokens'):
            raise RuntimeError('记忆整理输出被截断，请增加 API 最大输出长度。')
        return SimpleNamespace(completion_text=plain(result), is_chunk=False)

    async def text_chat_stream(self, **kwargs):
        yield await self.text_chat(**kwargs)


class OllamaEmbedding(EmbeddingProvider):
    provider_config = {'id': 'sunday-ollama'}

    def __init__(self, url, model):
        self.url, self.model, self.dimension = url, model, None

    def get_dim(self):
        if not self.dimension:
            raise RuntimeError('向量模型尚未验证。')
        return self.dimension

    async def get_embeddings(self, texts):
        def request():
            try:
                with requests.post(self.url + '/api/embed',
                                   json={'model': self.model, 'input': texts, 'truncate': False},
                                   timeout=(3, 120), allow_redirects=False) as response:
                    if response.status_code != 200:
                        raise RuntimeError(f'Ollama 向量请求失败（HTTP {response.status_code}）。')
                    values = response.json()['embeddings']
            except requests.RequestException:
                raise RuntimeError('Ollama 未运行或向量请求超时；请手动启动。') from None
            if len(values) != len(texts) or not values or not values[0]:
                raise RuntimeError('Ollama 返回的向量数量不正确。')
            dim = len(values[0])
            if self.dimension and dim != self.dimension:
                raise RuntimeError('向量维度已改变；请先恢复原模型或重建索引。')
            if any(len(v) != dim or not all(math.isfinite(x) for x in v) for v in values):
                raise RuntimeError('Ollama 返回了无效向量。')
            self.dimension = dim
            return values
        return await asyncio.to_thread(request)

    async def get_embedding(self, text):
        return (await self.get_embeddings([text]))[0]

    async def get_embeddings_batch(self, texts, batch_size=32, **kwargs):
        output = []
        for start in range(0, len(texts), batch_size):
            output.extend(await self.get_embeddings(texts[start:start + batch_size]))
        return output
