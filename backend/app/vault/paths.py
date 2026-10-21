"""Path guard: every vault write path must resolve inside the domain's vault."""

from pathlib import Path


class VaultPathError(ValueError):
    """A path would resolve outside the vault folder."""


def resolve_in_vault(vault_root: Path, *parts: str) -> Path:
    """Joins `parts` under `vault_root`, resolves symlinks and `..`, and
    returns the result only if it is still inside the vault."""
    root = vault_root.resolve()
    candidate = root.joinpath(*parts).resolve()
    if candidate != root and root not in candidate.parents:
        raise VaultPathError(f"path {'/'.join(parts)!r} resolves outside the vault {str(root)!r}")
    return candidate
