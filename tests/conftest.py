"""Shared pytest fixtures for dotfiles-drift tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _repo_ancestors(path: Path) -> list[str]:
    """Return every ancestor directory of ``path``, closest first."""
    ancestors: list[str] = []
    current = os.path.dirname(os.path.abspath(path))
    while True:
        ancestors.append(current)
        if current == os.sep:
            break
        current = os.path.dirname(current)
    return ancestors


@pytest.fixture
def non_git_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory that git will never resolve to an enclosing repository.

    ``git`` walks *up* the directory tree looking for a ``.git`` directory, so a
    ``tmp_path`` created inside somebody's checkout (e.g. ``TMPDIR`` pointing
    inside a home directory that is itself a git repo) is not a "non-git"
    directory at all: ``git ls-files`` succeeds there and every failure-path test
    silently degrades into a false "clean" result.

    Setting ``GIT_CEILING_DIRECTORIES`` to the ancestors of ``tmp_path`` stops
    git from ascending past it, which makes the directory genuinely outside any
    work tree regardless of where pytest happens to place its temporary files.

    Repositories created *inside* ``tmp_path`` keep working — the ceiling only
    prevents traversal upwards, not downwards — so tests that ``git init`` a
    real repo are unaffected.
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", os.pathsep.join(_repo_ancestors(tmp_path)))
    # Fail loudly rather than silently testing the wrong thing.
    probe = subprocess.run(
        ["git", "ls-files"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert probe.returncode != 0, (
        f"non_git_dir fixture failed: git resolved {tmp_path} to an enclosing "
        f"repository (git ls-files exited 0), so failure-path tests would be vacuous"
    )
    return tmp_path