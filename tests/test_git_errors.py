"""Tests for git failure propagation in dotfiles-drift scanner.

A ``git ls-files`` failure must never be reported as "no drift": the scanner has
to raise so the caller (and the CLI exit code) can distinguish "git says there
are no tracked files" from "git could not be read".
"""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from dotfiles_drift.scanner import GitLsFilesError, scan_drift


def _git_repo(path: Path) -> Path:
    """Create a real, empty git repository at ``path``."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], capture_output=True, check=True)
    return path


class TestOnlyTrackedGitFailure:
    """A failing ``git ls-files`` must surface, not yield an empty file list."""

    def test_non_git_dir_raises(self, non_git_dir, tmp_path):
        """Real git failure in a non-repo dir raises GitLsFilesError."""
        repo = non_git_dir / "dotfiles"
        repo.mkdir()
        (repo / ".bashrc").write_text("hello\n")
        home = tmp_path / "home"
        home.mkdir()
        (home / ".bashrc").write_text("hello\n")

        with pytest.raises(GitLsFilesError) as exc_info:
            scan_drift(repo, home, only_tracked=True)

        assert exc_info.value.returncode != 0
        assert exc_info.value.stderr.strip()
        assert "git ls-files failed" in str(exc_info.value)

    def test_failure_never_reports_clean_scan(self, non_git_dir, tmp_path):
        """The false negative must not be reachable: no ScanResult, no raise-free path."""
        repo = non_git_dir / "dotfiles"
        repo.mkdir()
        (repo / ".bashrc").write_text("hello\n")
        home = tmp_path / "home"
        home.mkdir()
        (home / ".bashrc").write_text("wrong content\n")

        with pytest.raises(GitLsFilesError):
            result = scan_drift(repo, home, only_tracked=True)
            pytest.fail(
                f"scanner silently degraded to a clean result "
                f"(repo_files={result.repo_files}, modified={result.modified})"
            )

    def test_called_process_error_preserves_details(self, tmp_path):
        """CalledProcessError is wrapped, keeping returncode and stderr."""
        repo = _git_repo(tmp_path / "dotfiles")
        home = tmp_path / "home"
        home.mkdir()
        (repo / ".bashrc").write_text("hello\n")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=128,
                cmd=["git", "ls-files"],
                stderr="fatal: detected dubious ownership in repository",
            )
            with pytest.raises(GitLsFilesError) as exc_info:
                scan_drift(repo, home, only_tracked=True)

        assert exc_info.value.returncode == 128
        assert "dubious ownership" in exc_info.value.stderr
        assert "dubious ownership" in str(exc_info.value)

    def test_called_process_error_empty_stderr(self, tmp_path):
        """Empty stderr still yields a message that names the exit code."""
        repo = _git_repo(tmp_path / "dotfiles")
        home = tmp_path / "home"
        home.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=2, cmd=["git", "ls-files"], stderr=""
            )
            with pytest.raises(GitLsFilesError) as exc_info:
                scan_drift(repo, home, only_tracked=True)

        assert exc_info.value.returncode == 2
        assert "exit code 2" in str(exc_info.value)

    def test_missing_git_binary_raises(self, tmp_path):
        """FileNotFoundError (no git binary) raises GitLsFilesError with code 127."""
        repo = _git_repo(tmp_path / "dotfiles")
        home = tmp_path / "home"
        home.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git")
            with pytest.raises(GitLsFilesError) as exc_info:
                scan_drift(repo, home, only_tracked=True)

        assert exc_info.value.returncode == 127
        assert "git executable not found" in str(exc_info.value)


class TestOnlyTrackedEmptyRepoIsLegitimate:
    """Exit code 0 with empty output is a real "no tracked files", not a failure."""

    def test_empty_repo_returns_zero_files(self, tmp_path):
        repo = _git_repo(tmp_path / "dotfiles")
        home = tmp_path / "home"
        home.mkdir()
        (repo / ".bashrc").write_text("hello\n")  # present but untracked

        result = scan_drift(repo, home, only_tracked=True)

        assert result.repo_files == 0

    def test_untracked_files_excluded_but_orphan_detected(self, tmp_path):
        repo = _git_repo(tmp_path / "dotfiles")
        home = tmp_path / "home"
        home.mkdir()
        (repo / ".bashrc").write_text("hello\n")
        subprocess.run(["git", "add", ".bashrc"], cwd=repo, capture_output=True, check=True)
        (home / ".zshrc").write_text("# zsh\n")

        result = scan_drift(repo, home, only_tracked=True)

        assert result.repo_files == 1
        assert [f.path for f in result.files if f.status == "missing"] == [".bashrc"]
        assert result.orphaned == 1