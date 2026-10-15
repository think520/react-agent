"""W1 E11 第一批：provider 层如实带回**停止原因**，循环据此做截断续写。

核对现状：全仓库没有 «finish_reason» —— 模型因为输出到上限被截断，循环看不出来，
于是把半截回答当成"完成"（"截断续写为零"）。参考项目的做法（报告 D4）：
«finish_reason=length» 不算完成，保留可见前缀继续写。
"""

from __future__ import annotations

from providers.openai_compat import OpenAICompatibleProvider
from providers.types import LLMResponse, LLMStreamChunk
from providers.stop_reason import was_truncated


def _provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        api_key="test-key", model="test-model",
        base_url="https://example.invalid", provider_name="test",
    )


def test_the_response_carries_the_stop_reason():
    response = _provider()._parse_response({
        "id": "req-1",
        "choices": [{
            "finish_reason": "length",
            "message": {"role": "assistant", "content": "写到一半"},
        }],
    })

    assert response.finish_reason == "length", response


def test_the_stream_chunk_carries_the_stop_reason():
    chunk = OpenAICompatibleProvider._parse_stream_chunk({
        "id": "req-1",
        "choices": [{"delta": {"content": "尾"}, "finish_reason": "stop"}],
    })

    assert chunk.finish_reason == "stop", chunk


def test_a_missing_stop_reason_stays_empty():
    response = _provider()._parse_response({
        "choices": [{"message": {"content": "没有说明为什么停"}}],
    })

    assert response.finish_reason == "", response


def test_was_truncated_only_for_length_like_reasons():
    for reason in ("length", "max_tokens", "max_output_tokens", "MAX_TOKENS"):
        assert was_truncated(reason) is True, reason
    for reason in ("stop", "tool_calls", "content_filter", "", None, "some_new_reason"):
        assert was_truncated(reason) is False, reason


def test_the_types_default_to_no_reason():
    assert LLMResponse().finish_reason == ""
    assert LLMStreamChunk().finish_reason == ""
