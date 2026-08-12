"""Pytest isolation for provider catalog (P5G.4).

`ProviderFactory.load_config` merges `~/.bobodan/provider.json` and may
migrate legacy config on first run. Tests must never read or write the
real user home, so route the catalog to a throwaway directory.
"""

import os
import tempfile

_ISOLATED_HOME = tempfile.mkdtemp(prefix="bobodan-test-home-")


def pytest_configure(config):
    os.environ.setdefault("BOBODAN_HOME", _ISOLATED_HOME)
