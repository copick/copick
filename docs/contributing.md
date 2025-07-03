# Contributing to Copick

We welcome contributions to copick! Whether you're reporting bugs, suggesting features, improving documentation, or contributing code, your help is appreciated.

## Getting Started

### Development Setup

1. **Fork and clone the repository**:
   ```bash
   git fork https://github.com/copick/copick.git
   git clone https://github.com/<your-username>/copick.git
   cd copick
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install with development dependencies**:
   ```bash
   pip install -e ".[dev,test]"
   ```

4. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

5. **Run tests to ensure everything is working**:
   ```bash
   pytest
   ```

### Development Commands

All development commands are documented in [`CLAUDE.md`](../CLAUDE.md) for AI assistants, but here are the key ones:

#### Testing
```bash
# Run all tests
pytest

# Run a specific test file
pytest tests/test_filesystem.py

# Run with coverage
pytest --cov=copick

# Run all tests including integration tests (default)
RUN_ALL=1 pytest

# Run only fast tests (skip integration tests)
RUN_ALL=0 pytest
```

#### Code Quality
```bash
# Format code with black
black src/ tests/

# Lint with ruff
ruff check src/ tests/

# Fix auto-fixable ruff issues
ruff check --fix src/ tests/

# Run pre-commit hooks
pre-commit run --all-files
```

#### Documentation
```bash
# Serve documentation locally
mkdocs serve

# Build documentation
mkdocs build
```

## Commit Message Guidelines

All pull requests must use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages. This helps us automatically generate changelogs and determine version bumps.

### Format
```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Types
- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation only changes
- `style`: Changes that do not affect the meaning of the code (white-space, formatting, etc)
- `refactor`: A code change that neither fixes a bug nor adds a feature
- `perf`: A code change that improves performance
- `test`: Adding missing tests or correcting existing tests
- `build`: Changes that affect the build system or external dependencies
- `ci`: Changes to our CI configuration files and scripts
- `chore`: Other changes that don't modify src or test files

### Examples
```bash
feat: add support for new tomogram format
fix: resolve memory leak in zarr loading
docs: update installation instructions
test: add unit tests for mesh operations
refactor: simplify configuration loading logic
perf: optimize zarr array reading for large volumes
```

## Plugin Development

Copick supports a plugin system that allows external Python packages to register CLI commands.

### Creating a Plugin

1. **In your package's `setup.py` or `pyproject.toml`**, add an entry point in the `copick.commands` group:

   **setup.py**:
   ```python
   setup(
       name="my-copick-plugin",
       entry_points={
           "copick.commands": [
               "my-command=my_package.cli:my_command",
           ],
       },
   )
   ```

   **pyproject.toml**:
   ```toml
   [project.entry-points."copick.commands"]
   my-command = "my_package.cli:my_command"
   ```

2. **Create a Click command** in your package:
   ```python
   import click

   from copick.cli.util import add_config_option, add_debug_option
   from copick.util.log import get_logger

   @click.command()
   @add_config_option
   @add_debug_option
   @click.pass_context
   def my_command(ctx, config: str, debug: bool):
       """My custom copick command."""
       logger = get_logger(__name__, debug=debug)
       logger.info(f"Running my command with config: {config}")
   ```

3. **After installing your package**, the command will be available via:
   ```bash
   copick my-command --config path/to/config.json --run TS_001
   ```

Thank you for contributing to copick! 🚀
