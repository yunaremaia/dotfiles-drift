"""CLI behaviour when ``git ls-files`` fails."""
from pathlib import Path
from subprocess import run as sp_run

import pytest
from click.testing import CliRunner

from dotfiles_drift.cli import cli


class TestStatusExitsNonZeroOnGitFailure:
    def test_status_reports_git_failure_and_exits_1(self, non_git_dir: Path, tmp_path: Path):
        repo = non_git_dir / "dotfiles"
        repo.mkdir()
        (repo / ".bashrc").write_text("hello\n")
        home = tmp_path / "home"
        home.mkdir()
        (home / ".bashrc").write_text("different\n")

        result = CliRunner().invoke(
            cli, ["status", str(repo), "--home", str(home), "--only-tracked"]
        )

        assert result.exit_code == 1
        assert "ERROR: git ls-files failed" in result.output

    def test_status_does_not_print_a_clean_summary(self, non_git_dir: Path, tmp_path: Path):
        """The failure path must never print a drift summary table."""
        repo = non_git_dir / "dotfiles"
        repo.mkdir()
        (repo / ".bashrc").write_text("hello\n")
        home = tmp_path / "home"
        home.mkdir()

        result = CliRunner().invoke(
            cli, ["status", str(repo), "--home", str(home), "--only-tracked"]
        )

        assert "Summary:" not in result.output

    def test_sync_reports_git_failure_and_exits_1(self, non_git_dir: Path, tmp_path: Path):
        repo = non_git_dir / "dotfiles"
        repo.mkdir()
        (repo / ".bashrc").write_text("hello\n")
        home = tmp_path / "home"
        home.mkdir()

        result = CliRunner().invoke(
            cli, ["sync", str(repo), "--home", str(home), "--only-tracked"]
        )

        assert result.exit_code == 1
        assert "ERROR: git ls-files failed" in result.output

    def test_status_succeeds_on_a_real_repo(self, tmp_path: Path):
        """Sanity: the success path still exits 0."""
        repo = tmp_path / "dotfiles"
        repo.mkdir()
        sp_run(["git", "init", "-q", str(repo)], capture_output=True, check=True)
        (repo / ".bashrc").write_text("hello\n")
        sp_run(["git", "add", ".bashrc"], cwd=repo, capture_output=True, check=True)
        home = tmp_path / "home"
        home.mkdir()
        (home / ".bashrc").write_text("hello\n")

        result = CliRunner().invoke(
            cli, ["status", str(repo), "--home", str(home), "--only-tracked"]
        )

        assert result.exit_code == 0
        assert ".bashrc" in result.output