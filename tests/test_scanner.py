"""Tests for dotfiles-drift scanner."""
import pytest
from pathlib import Path
from dotfiles_drift.scanner import scan_drift, apply_sync, _hash_file, _is_text_file


@pytest.fixture
def tmp_dotfiles(tmp_path):
    """Create a minimal dotfiles repo + fake home."""
    repo = tmp_path / "dotfiles"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    # Repo has these files
    (repo / ".bashrc").write_text("# bash config\nalias ll='ls -la'\n")
    (repo / ".gitconfig").write_text("[user]\n  name = Test\n")
    (repo / ".vimrc").write_text("set number\n")

    # Home has bashrc (same), gitconfig (different), and a file not in repo
    (home / ".bashrc").write_text("# bash config\nalias ll='ls -la'\n")
    (home / ".gitconfig").write_text("[user]\n  name = Changed\n")
    (home / ".zshrc").write_text("# zsh\n")  # orphaned

    return repo, home


class TestHashFile:
    def test_consistent(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        h1 = _hash_file(f)
        h2 = _hash_file(f)
        assert h1 == h2

    def test_different_content(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("a")
        f2.write_text("b")
        assert _hash_file(f1) != _hash_file(f2)


class TestScanDrift:
    def test_basic_drift(self, tmp_dotfiles):
        repo, home = tmp_dotfiles
        result = scan_drift(repo, home)
        assert result.repo_files == 3
        assert result.synced >= 1  # .bashrc
        assert result.modified >= 1  # .gitconfig
        assert result.missing >= 1  # .vimrc
        assert result.orphaned >= 1  # .zshrc

    def test_status_values(self, tmp_dotfiles):
        repo, home = tmp_dotfiles
        result = scan_drift(repo, home)
        for f in result.files:
            assert f.status in ("synced", "modified", "missing", "orphaned")

    def test_all_synced(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        home = tmp_path / "home"
        home.mkdir()
        (repo / ".bashrc").write_text("alias x=y\n")
        (home / ".bashrc").write_text("alias x=y\n")
        result = scan_drift(repo, home)
        assert result.synced == 1
        assert result.modified == 0
        assert result.missing == 0

    def test_only_tracked(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        home = tmp_path / "home"
        home.mkdir()
        (repo / ".bashrc").write_text("hello\n")
        (home / ".bashrc").write_text("hello\n")
        # git init to enable --tracked mode
        import subprocess
        subprocess.run(["git", "init", str(repo)], capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
        result = scan_drift(repo, home, only_tracked=True)
        assert result.synced >= 1


class TestApplySync:
    def test_dry_run_no_changes(self, tmp_dotfiles):
        repo, home = tmp_dotfiles
        result = scan_drift(repo, home)
        actions = apply_sync(repo, home, result, dry_run=True)
        # Should NOT copy anything on dry run
        assert any(a["action"] == "would_copy" for a in actions)

    def test_real_copy(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        home = tmp_path / "home"
        home.mkdir()
        (repo / ".newfile").write_text("content\n")
        result = scan_drift(repo, home)
        assert result.missing == 1
        apply_sync(repo, home, result, dry_run=False)
        assert (home / ".newfile").exists()
        assert (home / ".newfile").read_text() == "content\n"
