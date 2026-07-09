"""Server-Sent Events helpers."""

from __future__ import annotations

import json
from typing import Any


def encode_sse(event: str, data: Any) -> str:
    """Encode one SSE frame.

    Data is JSON-serialized so clients receive one stable object per event.
    """
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"
