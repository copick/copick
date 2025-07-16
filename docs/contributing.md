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

Copick supports a plugin system that allows external Python packages to register CLI commands. Commands can be added to the main CLI or organized into groups like `inference`, `training`, `evaluation`, `process`, and `convert`.

### Supported Entry Point Groups

The plugin system supports the following entry point groups:

- **`copick.commands`**: Commands added directly to the main CLI (e.g., `copick mycommand`)
- **`copick.inference.commands`**: Commands under the inference group (e.g., `copick inference mymodel`)
- **`copick.training.commands`**: Commands under the training group (e.g., `copick training mytrain`)
- **`copick.evaluation.commands`**: Commands under the evaluation group (e.g., `copick evaluation myscore`)
- **`copick.process.commands`**: Commands under the process group (e.g., `copick process mymethod`)
- **`copick.convert.commands`**: Commands under the convert group (e.g., `copick convert myconverter`)

### Creating a Plugin

1. **Set up your package structure**:
   ```
   my-copick-plugin/
   ├── src/
   │   └── my_copick_plugin/
   │       ├── __init__.py
   │       └── cli/
   │           ├── __init__.py
   │           └── cli.py
   ├── pyproject.toml
   └── README.md
   ```

2. **In your package's `pyproject.toml`**, add entry points for the desired groups:
   ```toml
   # Commands added to main CLI group
   [project.entry-points."copick.commands"]
   mycommand = "my_copick_plugin.cli.cli:mycommand"

   # Commands added to inference group
   [project.entry-points."copick.inference.commands"]
   mymodel-infer = "my_copick_plugin.cli.cli:mymodel_infer"

   # Commands added to training group
   [project.entry-points."copick.training.commands"]
   mymodel-train = "my_copick_plugin.cli.cli:mymodel_train"

   # Commands added to evaluation group
   [project.entry-points."copick.evaluation.commands"]
   myscore = "my_copick_plugin.cli.cli:myscore"

   # Commands added to process group
   [project.entry-points."copick.process.commands"]
   mymethod = "my_copick_plugin.cli.cli:mymethod"

   # Commands added to convert group
   [project.entry-points."copick.convert.commands"]
   myconverter = "my_copick_plugin.cli.cli:myconverter"
   ```

3. **Create Click commands** in your package:
   ```python
   import click

   from copick.cli.util import add_config_option, add_debug_option
   from copick.util.log import get_logger

   @click.command(short_help="A command added to the main copick CLI.")
   @add_config_option
   @click.option("--option", "-o", type=str, default=None, help="An example option.")
   @add_debug_option
   @click.pass_context
   def mycommand(ctx: click.Context, config: str, option: str, debug: bool):
       """A command that serves as an example for how to implement a CLI command in copick."""
       logger = get_logger(__name__, debug=debug)
       logger.info(f"Running mycommand with config: {config}, option: {option}")
       # Add your command logic here

   @click.command(short_help="An inference command.")
   @add_config_option
   @click.option("--model-path", type=str, help="Path to model file.")
   @add_debug_option
   @click.pass_context
   def mymodel_infer(ctx: click.Context, config: str, model_path: str, debug: bool):
       """A command that serves as an example for how to implement an inference CLI command in copick."""
       logger = get_logger(__name__, debug=debug)
       logger.info(f"Running inference with model: {model_path}")
       # Add your inference logic here
   ```

4. **After installing your package**, the commands will be available via:
   ```bash
   copick mycommand --config path/to/config.json --option value
   copick inference mymodel-infer --config path/to/config.json --model-path ./model.pt
   copick training mymodel-train --config path/to/config.json
   copick evaluation myscore --config path/to/config.json
   copick process mymethod --config path/to/config.json
   copick convert myconverter --config path/to/config.json
   ```

### Demo Package

A complete demo package is available at [copick-plugin-demo](https://github.com/copick/copick-plugin-demo) that demonstrates:

- Project structure for copick plugins
- Commands for all supported entry point groups
- Proper use of copick utilities like `add_config_option` and `add_debug_option`
- Entry point configuration in `pyproject.toml`
- Example command implementations

You can use this demo as a template for creating your own copick plugins.

Thank you for contributing to copick! 🚀
