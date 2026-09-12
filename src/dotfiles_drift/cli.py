"""CLI interface for dotfiles-drift."""
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .scanner import scan_drift, apply_sync, ScanResult

console = Console()


def _result_table(result: ScanResult) -> Table:
    table = Table(title=f"Dotfiles Drift — {result.repo_path}")
    table.add_column("File", style="white")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="dim")

    status_styles = {
        "synced": "green",
        "missing": "red",
        "modified": "yellow",
        "orphaned": "cyan",
    }

    for fs in sorted(result.files, key=lambda f: (f.status != "modified", f.status != "missing", f.path)):
        style = status_styles.get(fs.status, "white")
        details = ""
        if fs.status == "modified" and fs.repo_mtime and fs.home_mtime:
            from datetime import datetime
            repo_t = datetime.fromtimestamp(fs.repo_mtime).strftime("%Y-%m-%d")
            home_t = datetime.fromtimestamp(fs.home_mtime).strftime("%Y-%m-%d")
            details = f"repo={repo_t} home={home_t}"
        elif fs.status == "missing":
            details = "exists in repo, not in $HOME"
        elif fs.status == "orphaned":
            details = "exists in $HOME, not in repo"
        table.add_row(fs.path, f"[{style}]{fs.status}[/{style}]", details)

    return table


@click.group()
def cli():
    """Detect drift between your dotfiles repo and $HOME."""
    pass


@cli.command()
@click.argument("repo", type=click.Path(exists=True, file_okay=False))
@click.option("--home", type=click.Path(), default=str(Path.home()), help="Path to $HOME")
@click.option("--only-tracked", is_flag=True, help="Only check git-tracked files")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
def status(repo, home, only_tracked, fmt):
    """Show drift status."""
    result = scan_drift(Path(repo), Path(home), only_tracked=only_tracked)
    if fmt == "json":
        console.print(json.dumps({
            "repo": result.repo_path,
            "home": result.home_path,
            "synced": result.synced,
            "missing": result.missing,
            "modified": result.modified,
            "orphaned": result.orphaned,
            "files": [
                {"path": f.path, "status": f.status}
                for f in result.files
            ],
        }, indent=2))
    else:
        console.print(_result_table(result))
        console.print(
            f"\n[bold]Summary:[/bold] "
            f"[green]{result.synced} synced[/green] | "
            f"[red]{result.missing} missing[/red] | "
            f"[yellow]{result.modified} modified[/yellow] | "
            f"[cyan]{result.orphaned} orphaned[/cyan]"
        )


@cli.command()
@click.argument("repo", type=click.Path(exists=True, file_okay=False))
@click.option("--home", type=click.Path(), default=str(Path.home()), help="Path to $HOME")
@click.option("--only-tracked", is_flag=True, help="Only check git-tracked files")
@click.option("--dry-run", is_flag=True, help="Show what would be copied without doing it")
@click.option("--force", is_flag=True, help="Apply even if it overwrites")
def sync(repo, home, only_tracked, dry_run, force):
    """Sync repo files to $HOME."""
    result = scan_drift(Path(repo), Path(home), only_tracked=only_tracked)
    actions = apply_sync(Path(repo), Path(home), result, dry_run=not force)

    if not actions:
        console.print("[green]Nothing to sync.[/green]")
        return

    console.print(Panel(f"{'DRY RUN' if dry_run else 'SYNC'} — {len(actions)} files"))
    for a in actions:
        console.print(f"  [yellow]{a['action']}[/yellow] {a['src']} → {a['dst']}")

    if dry_run:
        console.print("\n[dim]Use --force to apply[/dim]")


def main():
    cli()


if __name__ == "__main__":
    main()
