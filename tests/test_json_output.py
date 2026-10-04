"""``status --format json`` must be machine-readable, not merely pretty.

``--format json`` exists so the report can be piped into another tool. Printing
the document through ``rich.Console`` makes it look like JSON while silently
producing output no parser can read, so every assertion here is a real parse of
the captured output, not a substring match.
"""
import json
from pathlib import Path
from subprocess import run as sp_run

from click.testing import CliRunner

from dotfiles_drift.cli import cli


def _make_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A real git repo whose drifted file forces a non-empty report."""
    repo = tmp_path / "dotfiles"
    repo.mkdir()
    sp_run(["git", "init", "-q", str(repo)], capture_output=True, check=True)
    (repo / ".bashrc").write_text("from the repo\n")
    sp_run(["git", "add", ".bashrc"], cwd=repo, capture_output=True, check=True)
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bashrc").write_text("different from the repo\n")
    return repo, home


class TestJsonFormatIsParseable:
    def test_output_parses_as_json(self, tmp_path: Path):
        repo, home = _make_repo(tmp_path)

        result = CliRunner().invoke(
            cli,
            ["status", str(repo), "--home", str(home), "--only-tracked", "--format", "json"],
        )

        assert result.exit_code == 0
        report = json.loads(result.output)
        assert report["modified"] == 1
        assert [f["path"] for f in report["files"]] == [".bashrc"]

    def test_counts_agree_with_the_file_list(self, tmp_path: Path):
        """Every per-status count must equal what the file list actually holds.

        A count that disagrees with the list is a report a user cannot trust to
        decide whether to re-run ``sync``.
        """
        repo, home = _make_repo(tmp_path)

        result = CliRunner().invoke(
            cli,
            ["status", str(repo), "--home", str(home), "--only-tracked", "--format", "json"],
        )
        report = json.loads(result.output)

        counted = {}
        for entry in report["files"]:
            counted[entry["status"]] = counted.get(entry["status"], 0) + 1
        assert len(report["files"]) == (
            report["synced"] + report["missing"] + report["modified"] + report["orphaned"]
        )
        for status, n in counted.items():
            assert report[status] == n

    def test_survives_a_narrow_terminal(self, tmp_path: Path, monkeypatch):
        """A wrapped line must not become a broken line.

        ``rich`` word-wraps to the console width and re-indents continuation
        lines, which corrupts string literals in the document. A user who pipes
        ``status`` into ``jq`` from a narrow terminal got a parse error with no
        hint about the cause.
        """
        repo, home = _make_repo(tmp_path)
        monkeypatch.setenv("COLUMNS", "40")

        result = CliRunner().invoke(
            cli, ["status", str(repo), "--home", str(home), "--format", "json"]
        )

        assert result.exit_code == 0
        assert json.loads(result.output)["modified"] == 1

    def test_long_paths_are_not_wrapped(self, tmp_path: Path):
        """The failure mode is width-driven, so use a genuinely long path.

        No ``COLUMNS`` override here: at the default width a deep checkout path
        alone exceeds it, which is what a user in a nested directory hits.
        """
        deep = tmp_path / "a-much-longer-checkout-directory-name" / "still" / "nested" / "here"
        deep.mkdir(parents=True)
        repo = deep / "dotfiles"
        repo.mkdir()
        sp_run(["git", "init", "-q", str(repo)], capture_output=True, check=True)
        (repo / ".bashrc").write_text("from the repo\n")
        sp_run(["git", "add", ".bashrc"], cwd=repo, capture_output=True, check=True)
        home = deep / "home"
        home.mkdir()
        (home / ".bashrc").write_text("different from the repo\n")

        result = CliRunner().invoke(
            cli,
            ["status", str(repo), "--home", str(home), "--only-tracked", "--format", "json"],
        )

        assert result.exit_code == 0
        report = json.loads(result.output)
        assert report["repo"] == str(repo)
        assert report["home"] == str(home)

    def test_path_with_markup_characters_survives(self, tmp_path: Path):
        """Square brackets in a filename are JSON, not rich markup.

        ``rich`` treats ``[...]`` as a style tag and eats it, so a dotfile named
        ``.[profile]`` was silently dropped from the report -- the file vanished
        from the drift listing instead of being listed as modified or missing.
        """
        repo = tmp_path / "dotfiles"
        repo.mkdir()
        sp_run(["git", "init", "-q", str(repo)], capture_output=True, check=True)
        (repo / ".[profile]").write_text("from the repo\n")
        sp_run(["git", "add", ".[profile]"], cwd=repo, capture_output=True, check=True)
        home = tmp_path / "home"
        home.mkdir()
        (home / ".[profile]").write_text("different from the repo\n")

        result = CliRunner().invoke(
            cli,
            ["status", str(repo), "--home", str(home), "--only-tracked", "--format", "json"],
        )

        assert result.exit_code == 0
        report = json.loads(result.output)
        assert [f["path"] for f in report["files"]] == [".[profile]"]
        assert report["modified"] == 1

    def test_json_output_has_no_decoration(self, tmp_path: Path):
        """Nothing may precede or follow the document.

        The human-readable path prints a rich panel and a summary line; those
        must not leak into the machine-readable one.
        """
        repo, home = _make_repo(tmp_path)

        result = CliRunner().invoke(
            cli,
            ["status", str(repo), "--home", str(home), "--only-tracked", "--format", "json"],
        )

        assert result.output.strip().startswith("{")
        assert result.output.strip().endswith("}")
        assert "Summary:" not in result.output