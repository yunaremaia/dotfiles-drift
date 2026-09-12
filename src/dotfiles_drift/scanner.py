"""Core scanner for dotfiles drift detection."""
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict


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
    """
    import fnmatch

    ignore = ignore_patterns or [".git", ".gitignore", ".gitmodules", "README.md", "LICENSE", "*.bak", "*.swp", "install.sh", "Makefile"]
    result = ScanResult(repo_path=str(repo_path), home_path=str(home_path))

    # Determine which files to check in repo
    if only_tracked:
        # Use git ls-files
        import subprocess
        try:
            out = subprocess.check_output(
                ["git", "ls-files"], cwd=str(repo_path), text=True
            )
            repo_files = [p.strip() for p in out.splitlines() if p.strip()]
        except Exception:
            repo_files = []
    else:
        repo_files = []
        for p in repo_path.rglob("*"):
            if p.is_file():
                rel = p.relative_to(repo_path).as_posix()
                if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(Path(rel).name, pat) for pat in ignore):
                    continue
                repo_files.append(rel)

    result.repo_files = len(repo_files)

    # Collect home files (top-level dotfiles only, plus common config dirs)
    home_files_map: dict[str, Path] = {}
    for p in home_path.iterdir():
        if p.name.startswith(".") and p.is_file():
            rel = p.name
            if not any(fnmatch.fnmatch(rel, pat) for pat in ignore):
                home_files_map[rel] = p
    # Also check common subdirs
    for subdir in [".config", ".local/bin"]:
        sub = home_path / subdir
        if sub.exists():
            for p in sub.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(home_path).as_posix()
                    if not any(fnmatch.fnmatch(Path(rel).name, pat) for pat in ignore):
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
