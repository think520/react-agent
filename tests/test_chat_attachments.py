"""Tests for ad-hoc chat image & file attachments."""

from __future__ import annotations

from providers.openai_compat import OpenAICompatibleProvider
from service.chat_attachment_service import MAX_EXTRACTED_CHARS, extract_chat_file


def test_extract_chat_file_reads_code_and_markdown():
    res = extract_chat_file("notes.py", "def fib(n):\n    return n\n".encode("utf-8"), "text/x-python")
    assert res["ok"] is True
    att = res["attachment"]
    assert att["type"] == "file"
    assert att["name"] == "notes.py"
    assert "def fib(n):" in att["text"]
    assert att["truncated"] is False


def test_extract_chat_file_truncates_large_text_and_rejects_binary():
    big = ("a" * (MAX_EXTRACTED_CHARS + 500)).encode("utf-8")
    res = extract_chat_file("big.txt", big, "text/plain")
    assert res["ok"] is True
    assert res["attachment"]["truncated"] is True
    assert len(res["attachment"]["text"]) == MAX_EXTRACTED_CHARS

    bad = extract_chat_file("archive.bin", b"\x00\x01\x02\x03", "application/octet-stream")
    assert bad["ok"] is False
    assert bad["code"] == "unsupported_attachment_type"


def test_openai_compat_formats_image_and_file_attachments():
    provider = OpenAICompatibleProvider(
        api_key="test",
        model="gpt-4o",
        base_url="https://api.example.com/v1",
        provider_name="openai",
    )
    converted = provider._convert_messages([
        {
            "role": "user",
            "content": "看看这张图和代码",
            "attachments": [
                {"type": "file", "name": "a.py", "text": "x = 1", "truncated": False},
                {"type": "image", "name": "shot.png", "mime_type": "image/png", "data_url": "data:image/png;base64,AAAA"},
            ],
        },
        {"role": "user", "content": "普通文本消息"},
    ])

    first = converted[0]["content"]
    assert isinstance(first, list)
    assert first[0]["type"] == "text"
    assert '<attached_file name="a.py">' in first[0]["text"]
    assert first[1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    assert converted[1]["content"] == "普通文本消息"


def test_openai_compat_explains_vision_unsupported_error():
    provider = OpenAICompatibleProvider(
        api_key="test",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        provider_name="deepseek",
    )
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看图"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                ],
            }
        ]
    }
    err = provider._api_error(400, '{"error":{"message":"unknown variant `image_url`, expected `text`"}}', payload)
    assert "不支持图片输入" in str(err)
    assert "deepseek-chat" in str(err)
