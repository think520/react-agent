"""The suite must not touch the repository's own runtime databases."""

import os

from web.backend.deps import get_workspace


def test_workspace_is_isolated_from_the_repository():
    # tests/conftest.py pins BOBODAN_WORKSPACE. Without that pin, any store built
    # without an explicit workspace opens the repo's real .knowledge/bobodan.db and
    # silently migrates it (this happened once and is why the pin exists).
    repository = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    workspace = os.path.abspath(get_workspace())
    assert not workspace.startswith(repository + os.sep), workspace
