# dotfiles-drift

**Detect drift between your dotfiles repo and $HOME.**

Answer the question: *"What changed on my machine that's not in my dotfiles repo, and vice versa?"*

![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Why

You keep your dotfiles in a git repo. You clone it onto a new machine. But which files did you forget to add? Which files exist in `$HOME` but not in the repo? Which files have been modified locally without being committed?

`dotfiles-drift` tells you:

| Status | Meaning |
|--------|---------|
| **synced** | Repo and home have identical content |
| **missing** | File exists in repo but not in home (need to symlink/copy) |
| **modified** | File exists in both but content differs |
| **orphaned** | File exists in home but not in repo |

## Install

```bash
pip install git+https://github.com/yunaremaia/dotfiles-drift.git
```

## Usage

```bash
# Check drift status
dotfiles-drift status ~/dotfiles

# Export as JSON
dotfiles-drift status ~/dotfiles --format json

# Sync missing/modified files from repo to home (dry run)
dotfiles-drift sync ~/dotfiles --dry-run

# Actually sync
dotfiles-drift sync ~/dotfiles --force

# Only check git-tracked files
dotfiles-drift status ~/dotfiles --only-tracked
```

## Example Output

```
Dotfiles Drift — /root/dotfiles
┏━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ File          ┃ Status   ┃ Details                            ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ .bashrc      │ [green]synced │                              │
│ .gitconfig   │ [yellow]modified│ repo=2026-09-12 home=2026-08-30│
│ .vimrc       │ [red]missing │ exists in repo, not in $HOME      │
│ .zshrc       │ [cyan]orphaned│ exists in $HOME, not in repo     │
└──────────────┴──────────┴────────────────────────────────────┘

Summary: 1 synced | 1 missing | 1 modified | 1 orphaned
```

## Features

- SHA256 content comparison (not just size/mtime)
- Detects orphaned files (exist in `$HOME` but not in repo)
- Git-tracked-only mode
- JSON output for scripting
- Dry-run sync mode
- Ignores `.git`, `README.md`, `LICENSE`, `Makefile`, `*.bak`, `*.swp` by default

## Alternatives

- [GNU Stow](https://www.gnu.org/software/stow/) — symlink manager, not drift detector
- [yadm](https://yadm.io/) — dotfiles manager with git, but no drift reporting
- [chezmoi](https://chezmoi.io/) — has `chezmoi diff` but heavier tool
- [rcm](https://github.com/thoughtbot/rcm) — rc file management, no content diff

`dotfiles-drift` is a **read-only detector** — it reports what's out of sync. You decide whether to symlink, copy, or use a full dotfiles manager.

## License

MIT
