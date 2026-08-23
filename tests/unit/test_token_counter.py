# 功能：验证 CJK 回退估算显著优于 len//4（中文按约 1 token/字符）
# 设计：用不存在的编码名强制走字符回退路径（不依赖 tiktoken 是否安装），
#      中文文本的估算必须明显大于 len//4，否则压缩判定会严重失真
from sztu_code.core.compact.token_counter import TokenCounter


# 功能：验证中文文本在回退路径下不被 len//4 低估
def test_cjk_fallback_beats_chars_per_4() -> None:
    counter = TokenCounter("nonexistent-encoding")
    text = "这是一个用于测试的中文句子" * 10  # 200 个中文字符
    estimated = counter.count(text)
    assert estimated > len(text) // 4 + 4


# 功能：验证英文文本在回退路径下仍按约 4 字符/token 估算
def test_ascii_fallback_approximates_chars_per_4() -> None:
    counter = TokenCounter("nonexistent-encoding")
    text = "hello world " * 20  # 240 个 ASCII 字符
    estimated = counter.count(text)
    assert 240 // 4 + 4 <= estimated <= 240 + 4


# 功能：验证空字符串计数仍返回正数
def test_empty_string_min_positive() -> None:
    counter = TokenCounter("nonexistent-encoding")
    assert counter.count("") >= 1


# 功能：验证 count_json 对空值返回 0、对结构与字符串正确计数
# 设计：空 dict/list/None/"" 不应计入 token，避免空工具输入污染压缩预估
def test_count_json_handles_empty_and_structured() -> None:
    counter = TokenCounter("nonexistent-encoding")
    assert counter.count_json(None) == 0
    assert counter.count_json("") == 0
    assert counter.count_json({}) == 0
    assert counter.count_json([]) == 0
    assert counter.count_json({"path": "a.py"}) >= 1
    assert counter.count_json([{"type": "tool_result", "content": "x"}]) >= 1


# 功能：验证 count_messages 对混合 content 格式（字符串 + 块列表）正确累计
def test_count_messages_mixed_content() -> None:
    counter = TokenCounter("nonexistent-encoding")
    messages = [
        {"role": "user", "content": "普通文本消息"},
        {"role": "assistant", "content": [{"type": "text", "text": "文本块"}]},
        {"role": "user", "content": [{"type": "tool_result", "content": "result"}]},
    ]
    total = counter.count_messages(messages)
    assert total > 0
    # 列表块只计 text/content 字段，不会对整条消息重复计数
    assert total <= sum(len(str(m)) for m in messages)


# 功能：验证同一编码名下多次构造共享同一编码器实例
# 设计：编码器加载是进程级缓存（lru_cache），每次 LLM 调用新建 TokenCounter
#      不应重复加载 tiktoken；断言实例 identity 相同，防性能回归
def test_encoder_instance_is_shared() -> None:
    a = TokenCounter("cl100k_base")
    b = TokenCounter("cl100k_base")
    assert a._encoder is b._encoder or (a._encoder is None and b._encoder is None)


# 功能：验证 count 与 count_json 对纯字符串结果一致
def test_count_json_string_matches_count() -> None:
    counter = TokenCounter("nonexistent-encoding")
    assert counter.count_json("hello") == counter.count("hello")
