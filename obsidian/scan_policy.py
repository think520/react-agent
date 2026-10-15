"""Scan policy shared by the vault scan and the material scans.

2026-09-24 (E17 ①): a GitHub download dropped README / CONTRIBUTING /
requirements.txt / _sidebar.md into the document list because only a
root-level `README.md` was skipped. The rule now lives here so the vault scan
and the material scans cannot drift apart again.
"""

#: Repository metadata: never study material, skipped at **any** level.
REPO_METADATA_FILENAMES = frozenset(
    {
        "readme.md",
        "contributing.md",
        "changelog.md",
        "changelog.txt",
        "license",
        "license.md",
        "license.txt",
        "_sidebar.md",
        "_navbar.md",
    }
)


def is_repo_metadata(filename: str) -> bool:
    lowered = filename.casefold()
    if lowered in REPO_METADATA_FILENAMES:
        return True
    return lowered.startswith("requirements") and lowered.endswith(".txt")
