"""Core scanner for dotfiles drift detection."""
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict


class GitLsFilesError(Exception):
    """Raised when the ``git ls-files`` command fails."""

    def __init__(self, message: str, returncode: int = 1, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


@dataclass
class FileStatus:
    path: str  # relative path from repo/home
    status: str  # synced, missing, modified, orphaned
    repo_hash: Optional[str] = None
    home_hash: Optional[str] = None
    repo_mtime: Optional[float] = None
    home_mtime: Optional[float] = None


@dataclass
class ScanResult:
    repo_path: str
    home_path: str
    files: list[FileStatus] = field(default_factory=list)
    scanned_at: str = ""
    repo_files: int = 0
    home_files: int = 0
    synced: int = 0
    missing: int = 0
    modified: int = 0
    orphaned: int = 0

    def __post_init__(self):
        if not self.scanned_at:
            self.scanned_at = datetime.utcnow().isoformat()


def _hash_file(filepath: Path) -> str:
    """Return SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_text_file(filepath: Path) -> bool:
    """Heuristic: try to decode as UTF-8."""
    try:
        filepath.read_text(encoding="utf-8")
        return True
    except (UnicodeDecodeError, PermissionError):
        return False


def _git_tracked_files(repo_path: Path) -> list[str]:
    """List git-tracked files in ``repo_path`` via ``git ls-files``.

    A failure is never treated as "no tracked files": an unreadable repository
    would otherwise yield a scan result with zero repo files, i.e. a false
    "no drift" report for a scan that never happened.

    Raises:
        GitLsFilesError: If git exits non-zero or the git executable is missing.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        err_msg = (
            e.stderr.strip()
            if e.stderr
            else f"git command failed with exit code {e.returncode}"
        )
        raise GitLsFilesError(
            f"git ls-files failed: {err_msg}",
            returncode=e.returncode,
            stderr=e.stderr or "",
        ) from e
    except OSError as e:
        raise GitLsFilesError(
            f"git ls-files failed: git executable not found ({e})",
            returncode=127,
        ) from e

    # Exit code 0 with empty stdout means git found no tracked files; that is a
    # legitimate empty result, unlike the failure paths above.
    return [p.strip() for p in result.stdout.splitlines() if p.strip()]


def _is_ignored(rel: str, ignore: list[str]) -> bool:
    """Check if a relative path matches any ignore pattern.

    Checks the full path and each path component against the ignore patterns.
    This ensures that files under an ignored directory (e.g. ``.git/HEAD``
    under ``.git/``) are also filtered.
    """
    import fnmatch
    if any(fnmatch.fnmatch(rel, pat) for pat in ignore):
        return True
    parts = Path(rel).parts
    return any(
        fnmatch.fnmatch(part, pat)
        for part in parts
        for pat in ignore
    )


def scan_drift(
    repo_path: Path,
    home_path: Path,
    ignore_patterns: Optional[list[str]] = None,
    only_tracked: bool = False,
) -> ScanResult:
    """Compare dotfiles repo against $HOME and report drift.

    Args:
        repo_path: Path to the dotfiles repository
        home_path: Path to $HOME
        ignore_patterns: Glob patterns to skip (e.g. ['.git', '*.bak'])
        only_tracked: If True, only check files tracked by git in repo

    Raises:
        GitLsFilesError: If only_tracked is True and ``git ls-files`` fails.
    """
    ignore = ignore_patterns or [".git", ".gitignore", ".gitmodules", "README.md", "LICENSE", "*.bak", "*.swp", "install.sh", "Makefile"]
    result = ScanResult(repo_path=str(repo_path), home_path=str(home_path))

    # Determine which files to check in repo
    if only_tracked:
        repo_files = _git_tracked_files(repo_path)
    else:
        repo_files = []
        for p in repo_path.rglob("*"):
            if p.is_file():
                rel = p.relative_to(repo_path).as_posix()
                if _is_ignored(rel, ignore):
                    continue
                repo_files.append(rel)

    result.repo_files = len(repo_files)

    # Collect home files (top-level dotfiles only, plus common config dirs)
    home_files_map: dict[str, Path] = {}
    for p in home_path.iterdir():
        if p.name.startswith(".") and p.is_file():
            rel = p.name
            if not _is_ignored(rel, ignore):
                home_files_map[rel] = p
    # Also check common subdirs
    for subdir in [".config", ".local/bin"]:
        sub = home_path / subdir
        if sub.exists():
            for p in sub.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(home_path).as_posix()
                    if not _is_ignored(rel, ignore):
                        home_files_map[rel] = p

    result.home_files = len(home_files_map)

    # Check each repo file
    seen_home = set()
    for rel in repo_files:
        repo_file = repo_path / rel
        home_file = home_path / rel

        repo_hash = _hash_file(repo_file) if repo_file.exists() else None
        repo_mtime = repo_file.stat().st_mtime if repo_file.exists() else None

        if home_file.exists():
            seen_home.add(rel)
            home_hash = _hash_file(home_file)
            home_mtime = home_file.stat().st_mtime
            if repo_hash == home_hash:
                status = "synced"
                result.synced += 1
            else:
                status = "modified"
                result.modified += 1
        else:
            status = "missing"
            home_hash = None
            home_mtime = None
            result.missing += 1

        result.files.append(FileStatus(
            path=rel,
            status=status,
            repo_hash=repo_hash,
            home_hash=home_hash,
            repo_mtime=repo_mtime,
            home_mtime=home_mtime,
        ))

    # Check for orphaned home files (exist in home but not in repo)
    for rel, home_file in home_files_map.items():
        if rel not in repo_files and rel not in seen_home:
            result.orphaned += 1
            result.files.append(FileStatus(
                path=rel,
                status="orphaned",
                home_hash=_hash_file(home_file),
                home_mtime=home_file.stat().st_mtime,
            ))

    return result


def apply_sync(
    repo_path: Path,
    home_path: Path,
    scan_result: ScanResult,
    dry_run: bool = True,
    force: bool = False,
) -> list[dict]:
    """Apply sync: copy missing/modified files from repo to home.

    Returns list of actions taken.
    """
    actions = []
    for fs in scan_result.files:
        if fs.status == "synced":
            continue
        if fs.status == "orphaned":
            continue  # Don't delete orphaned files automatically

        src = repo_path / fs.path
        dst = home_path / fs.path

        if not src.exists():
            continue

        if dry_run:
            actions.append({
                "action": "would_copy",
                "src": str(src),
                "dst": str(dst),
                "reason": fs.status,
            })
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(str(src), str(dst))
            actions.append({
                "action": "copied",
                "src": str(src),
                "dst": str(dst),
                "reason": fs.status,
            })

    return actions
