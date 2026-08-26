from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN_FALLBACK = 4  # 回退方案：非 CJK 字符每 token 约 4 个字符

# 每个文本块固定的结构开销（消息包装、JSON 括号、角色前缀等），缓解系统性低估
_BLOCK_STRUCTURE_OVERHEAD = 4

# CJK 常用区间（基本区 + 扩展 A/B + 兼容表意文字）— 中文按约 1 token/字符 估算
_CJK_RANGES = (
    (0x3400, 0x4DBF),   # CJK Extension A
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
    (0x20000, 0x2A6DF), # CJK Extension B
)


# 判断字符是否属于 CJK 表意文字区间
def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


# 按编码名加载 tiktoken 编码器；不可用时返回 None（结果被 lru_cache 缓存，跨实例共享）
@lru_cache(maxsize=8)
def _get_encoder(encoding_name: str) -> Any | None:
    try:
        import tiktoken  # type: ignore[import-not-found]
        return tiktoken.get_encoding(encoding_name)
    except (ImportError, ValueError):
        logger.debug("tiktoken 不可用，回退到字符估算 (name=%s)", encoding_name)
        return None


# 精确 Token 计数器，tiktoken 不可用时回退到 CJK 感知的字符估算
class TokenCounter:
    # 初始化；编码器按名称共享（同一进程内复用同一 tiktoken 实例，避免重复加载）
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self._encoding_name = encoding_name
        self._encoder = _get_encoder(encoding_name)

    # 计算文本的 token 数量（含固定结构开销）
    def count(self, text: str) -> int:
        if self._encoder is not None:
            try:
                return len(self._encoder.encode(text)) + _BLOCK_STRUCTURE_OVERHEAD
            except Exception:
                pass  # 编码失败时回退
        return self._fallback(text) + _BLOCK_STRUCTURE_OVERHEAD

    # 计算 JSON 可序列化值的 token 数量（内部统一序列化，供工具输入等结构计数）
    def count_json(self, value: Any) -> int:
        if value in (None, "", [], {}):
            return 0
        if isinstance(value, str):
            return self.count(value)
        return self.count(json.dumps(value, ensure_ascii=False, separators=(",", ":")))

    # 计算消息列表的总 token 数
    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "") or block.get("content", "")
                        if isinstance(text, str):
                            total += self.count(text)
        return max(1, total)

    # 精确 token 计数是否可用
    @property
    def precise_available(self) -> bool:
        return self._encoder is not None

    # 字符回退估算：CJK 字符按 1 token、其余按 1/4 token，向上取整
    @staticmethod
    def _fallback(text: str) -> int:
        if not text:
            return 0
        cjk = sum(1 for ch in text if _is_cjk(ch))
        non_cjk = len(text) - cjk
        return max(1, math.ceil(cjk + non_cjk / _CHARS_PER_TOKEN_FALLBACK))
