"""Pytest isolation for the provider catalog (P5G.4) and the workspace itself.

`ProviderFactory.load_config` merges `~/.bobodan/provider.json` and may migrate
legacy config on first run, and the default workspace is the current directory.
Tests must never read or write the real user home or a real workspace, so both
are routed to throwaway directories.
"""

import os
import tempfile

import pytest

_ISOLATED_HOME = tempfile.mkdtemp(prefix="bobodan-test-home-")
_ISOLATED_WORKSPACE = tempfile.mkdtemp(prefix="bobodan-test-workspace-")


def pytest_configure(config):
    os.environ.setdefault("BOBODAN_HOME", _ISOLATED_HOME)
    # Without this the suite silently opens (and migrates) the developer's own
    # `.knowledge/bobodan.db`. Verified both ways: dropping the pin makes the file
    # reappear, restoring it means no connection to that path is opened at all.
    # Tests that need a workspace still pass their own tmp_path to the store.
    os.environ.setdefault("BOBODAN_WORKSPACE", _ISOLATED_WORKSPACE)


@pytest.fixture
def scripted_provider():
    """Canonical fake LLM (R0.3). New tests must use this seam instead of
    declaring local FakeProvider classes — see tests/README.md."""
    from tests.llm_fake import ScriptedProvider

    provider = ScriptedProvider()
    yield provider
