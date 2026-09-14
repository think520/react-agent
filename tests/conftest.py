"""Pytest isolation for the provider catalog (P5G.4) and the workspace itself.

`ProviderFactory.load_config` merges `~/.bobodan/provider.json` and may migrate
legacy config on first run, and the default workspace is the current directory.
Tests must never read or write the real user home or a real workspace, so both
are routed to throwaway directories, and a tripwire fails the run if anything
still reaches the repository database.
"""

import os
import sys
import tempfile

import pytest

_ISOLATED_HOME = tempfile.mkdtemp(prefix="bobodan-test-home-")
_ISOLATED_WORKSPACE = tempfile.mkdtemp(prefix="bobodan-test-workspace-")

# The developer own workspace database. The suite must never write it.
_REPO_DB = os.path.abspath(os.path.join(os.getcwd(), ".knowledge", "bobodan.db"))
_REPO_DB_BEFORE = None


def _fingerprint(path):
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns)


def pytest_configure(config):
    global _REPO_DB_BEFORE
    _REPO_DB_BEFORE = _fingerprint(_REPO_DB)
    os.environ.setdefault("BOBODAN_HOME", _ISOLATED_HOME)
    # The default workspace is the current directory. Without this pin any store
    # built without an explicit workspace opens the repository database -- that
    # has silently migrated it before. The pin covers the environment-driven
    # paths; the tripwire below covers code that hardcodes "." or os.getcwd().
    os.environ.setdefault("BOBODAN_WORKSPACE", _ISOLATED_WORKSPACE)


def pytest_sessionfinish(session, exitstatus):
    if _REPO_DB_BEFORE is None or _fingerprint(_REPO_DB) == _REPO_DB_BEFORE:
        return
    session.exitstatus = 1
    print(
        "\n*** the test suite modified the real workspace database:\n"
        "    " + _REPO_DB + "\n"
        "*** A code path resolved the workspace from the current directory.\n"
        "*** Pass an explicit tmp_path workspace, or add monkeypatch.chdir(tmp_path).\n",
        file=sys.stderr,
    )


@pytest.fixture
def scripted_provider():
    """Canonical fake LLM (R0.3). New tests must use this seam instead of
    declaring local FakeProvider classes -- see tests/README.md."""
    from tests.llm_fake import ScriptedProvider

    provider = ScriptedProvider()
    yield provider
