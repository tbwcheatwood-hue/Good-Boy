"""Path containment for worktree cleanup, wiki reads, and skill imports.

``..``, absolute paths, and symlinks that resolve outside the sandbox are
rejected. Sensitive credential directories are rejected even when a caller
points the sandbox at a home directory.
"""

from __future__ import annotations

from pathlib import Path

_SENSITIVE_PARTS = frozenset(
    {
        ".ssh",
        ".aws",
        ".gnupg",
        ".kube",
        ".docker",
    }
)
_SENSITIVE_NAMES = frozenset(
    {
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "credentials.json",
        "credentials",
        ".env",
    }
)


def path_is_inside(root: Path, candidate: Path) -> bool:
    """True when ``candidate`` resolves inside ``root`` and is not a symlink escape."""
    try:
        root_resolved = root.resolve()
        resolved = candidate.resolve()
    except OSError:
        return False
    if resolved == root_resolved:
        return True
    return root_resolved in resolved.parents


def sensitive_relative(relative: Path) -> bool:
    """True for credential files and directories, whatever the sandbox root is."""
    parts = {part.lower() for part in relative.parts}
    if parts & _SENSITIVE_PARTS:
        return True
    name = relative.name.lower()
    return name in _SENSITIVE_NAMES or name.startswith(".env")
