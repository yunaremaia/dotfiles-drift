# Contributing to dotfiles-drift

## Getting Started

1. Fork the repository
2. Clone your fork 38. Create a virtual environment: `python -m venv venv && source venv/bin/activate`t
 4. Install dev dependencies: `pip install -e "[.dev]"`
5. Run tests: `pytest`

### Development Workflow
1. Create a feature branch from `main`: `git checkout -b feat/my-feature`
2. Make your changes
3. Run tests and linting
4. Commit with conventional commit format
5. Push and open a Pull Request

## Code Style

- Follow PEP 8
- Use type hints
- Write docstrings for public functions

## Testing

- Write tests for new functionality in `tests/`
- Ensure all tests pass before opening a PR
