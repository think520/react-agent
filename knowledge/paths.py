"""Storage paths shared by legacy workspaces and portable libraries."""

from __future__ import annotations

import os


def knowledge_dir(workspace: str) -> str:
    root = os.path.abspath(workspace)
    if os.path.isfile(os.path.join(root, "BOBODAN_LIBRARY.yaml")):
        return os.path.join(root, ".bobodan")
    return os.path.join(root, ".knowledge")


def knowledge_path(workspace: str, *parts: str) -> str:
    return os.path.join(knowledge_dir(workspace), *parts)
