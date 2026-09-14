"""Conservative token estimation shared by the compactor and the injector (P0-7).

`len(text) // 4` under-counted Chinese by roughly 4x. Measured on this
project own corpus with `cl100k_base`:

    25 Chinese characters -> 29 tokens  (about 1.16 per character)
    54 ASCII characters   ->  9 tokens  (about 1/6 per character)

Under-counting is the dangerous direction: it makes `should_compact` fire too
late and lets a nominal 1500-token memory budget admit several thousand tokens
of Chinese, which ends in a provider 400. So the wide-character weight is
measured-and-rounded-up, while latin text keeps the historical 1/4 (which
already over-estimates the measured 1/6 — also the safe direction).
"""

from __future__ import annotations

import math

# Chars at or above this code point are treated as wide: CJK ideographs and
# radicals, kana, hangul, fullwidth forms and emoji. Deliberately broad.
WIDE_FROM = 0x2E80
WIDE_TOKENS_PER_CHAR = 1.2
NARROW_TOKENS_PER_CHAR = 0.25


def is_wide(char: str) -> bool:
    """True for characters that a tokenizer roughly maps one-to-one."""
    return ord(char) >= WIDE_FROM


def estimate_tokens(text: str) -> int:
    """Return a deliberately conservative token estimate for mixed text."""
    if not text:
        return 0
    wide = sum(1 for char in text if is_wide(char))
    narrow = len(text) - wide
    return max(1, math.ceil(wide * WIDE_TOKENS_PER_CHAR + narrow * NARROW_TOKENS_PER_CHAR))
