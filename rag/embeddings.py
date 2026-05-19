import math
import re
from collections import Counter


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


class LocalEmbeddingProvider:
    """Deterministic sparse vector provider for the MVP local index."""

    def embed(self, text: str) -> dict[str, float]:
        tokens = [token.casefold() for token in TOKEN_RE.findall(text)]
        counts = Counter(tokens)
        norm = math.sqrt(sum(value * value for value in counts.values()))
        if not norm:
            return {}
        return {token: value / norm for token, value in counts.items()}


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(token, 0.0) for token, value in left.items())
