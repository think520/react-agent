"""P1-21: grep chunk ids must survive a process restart."""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_SCRIPT = ";".join([
    "import sys",
    "sys.path.insert(0, %r)" % str(REPO_ROOT),
    "from rag.grep_retriever import GrepMatch, _matches_to_hits",
    "m = GrepMatch(document_id='doc-1', source='a.md', text='t', "
    "match_context='同一段原文用于定位', match_type='exact_phrase', context_chars=5)",
    "print(_matches_to_hits([m], 'high', False, 200)[0].chunk_id)",
])


def _chunk_id(seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        check=True,
    )
    return result.stdout.strip()


def test_grep_chunk_id_is_stable_across_processes():
    """The id came from Python hash(), which PYTHONHASHSEED salts per process.

    A wrong-answer variant looks its source back up by chunk_id, so after a
    restart every id changed and the lookup missed.
    """
    first = _chunk_id("0")
    second = _chunk_id("1")
    assert first == second, (first, second)
    assert first.startswith("grep:doc-1:")
