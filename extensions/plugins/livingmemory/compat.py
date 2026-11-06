"""Small AstrBot host surface, installed only inside the isolated memory process.

The upstream engine, processor, lifecycle and dashboard remain byte-for-byte
upstream. This is not an implementation of the AstrBot plugin event bus.
"""
import enum
import logging
from pathlib import Path
import sys
import types


def install(vendor):
    def module(name, **attributes):
        obj = types.ModuleType(name)
        obj.__path__ = [str(Path(vendor).joinpath(*name.split('.')))]
        obj.__dict__.update(attributes)
        sys.modules[name] = obj
        if '.' in name:
            parent, _, child = name.rpartition('.')
            setattr(sys.modules[parent], child, obj)
        return obj

    logger = logging.getLogger('livingmemory')
    module('astrbot', logger=logger)
    module('astrbot.core', logger=logger)
    module('astrbot.api', logger=logger, sp=types.SimpleNamespace())
    module('astrbot.api.event', AstrMessageEvent=type('AstrMessageEvent', (), {}))
    module('astrbot.api.star', Context=type('Context', (), {}))
    class MessageType(enum.Enum):
        FRIEND_MESSAGE = 'FriendMessage'
        GROUP_MESSAGE = 'GroupMessage'
    module('astrbot.api.platform', MessageType=MessageType)
    module('astrbot.core.provider')
    module('astrbot.core.provider.provider', Provider=type('Provider', (), {}),
           EmbeddingProvider=type('EmbeddingProvider', (), {}),
           RerankProvider=type('RerankProvider', (), {}))
    class KnowledgeBaseUploadError(Exception):
        def __init__(self, user_message='', **kwargs):
            super().__init__(user_message)
    module('astrbot.core.exceptions', KnowledgeBaseUploadError=KnowledgeBaseUploadError)
    for name in ('astrbot.core.db', 'astrbot.core.db.vec_db',
                 'astrbot.core.knowledge_base', 'astrbot.core.knowledge_base.retrieval'):
        module(name)
    sys.path.insert(0, str(vendor))
