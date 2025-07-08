# CLI Reference

The Copick CLI provides a comprehensive set of commands for managing Copick projects, configurations, and data.

!!! tip "Environment Variable Support"
    The configuration file path can be set using the `COPICK_CONFIG` environment variable instead of passing `--config` every time:

    ```bash
    export COPICK_CONFIG=/path/to/config.json
    copick browse  # Uses config from environment variable
    ```

---

## Commands

### :material-eye: `copick browse`

Browse Copick projects interactively using a terminal user interface.

**Usage:**
```bash
copick browse [OPTIONS]
```

**Options:**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `-c, --config PATH` | Path | Path to the configuration file | Uses `COPICK_CONFIG` env var |
| `-ds, --dataset-ids ID` | Integer | Dataset IDs to include (multiple inputs possible) | None |
| `--debug / --no-debug` | Boolean | Enable debug logging | `no-debug` |

**Examples:**

```bash
# Browse a local project
copick browse --config my_project.json

# Browse CryoET Data Portal datasets
copick browse --dataset-ids 10000 --dataset-ids 10001

# Using environment variable
export COPICK_CONFIG=my_project.json
copick browse
```

---

### :material-cog: `copick config`

Manage Copick configuration files.

**Subcommands:**

- [`copick config dataportal`](#copick-config-dataportal) - Set up a configuration file from CZDP dataset IDs
- [`copick config filesystem`](#copick-config-filesystem) - Set up a configuration file for a local project


#### :material-database: `copick config dataportal`

Generate a configuration file from CryoET Data Portal datasets.

**Usage:**
```bash
copick config dataportal [OPTIONS]
```

**Options:**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `-ds, --dataset-id INTEGER` | Integer | Dataset IDs from the CryoET Data Portal (required, multiple allowed) | None |
| `--overlay TEXT` | Path | Path to the local overlay directory (required) | None |
| `--output TEXT` | Path | Path to save the generated configuration file | `config.json` |
| `--debug / --no-debug` | Boolean | Enable debug logging | `no-debug` |

**Examples:**

```bash
# Single dataset
copick config dataportal --dataset-id 10000 --overlay ./overlay --output my_config.json

# Multiple datasets
copick config dataportal -ds 10000 -ds 10001 --overlay ./overlay --output multi_config.json
```

#### :material-folder: `copick config filesystem`

Generate a configuration file for a local project directory.

**Usage:**
```bash
copick config filesystem [OPTIONS]
```

**Options:**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `--overlay-root TEXT` | Path | Overlay root path (required) | None |
| `--objects TEXT` | String | List of desired objects in the format: `name,is_particle,[radius],[pdb_id]` (required, multiple allowed) | None |
| `--config TEXT` | Path | Path to the output JSON configuration file | `config.json` |
| `--proj-name TEXT` | String | Name of the project configuration | `project` |
| `--proj-description TEXT` | String | Description of the project configuration | `Config Project for SessionXXa` |
| `--debug / --no-debug` | Boolean | Enable debug logging | `no-debug` |

**Object Format:**
Objects are specified using the format: `name,is_particle,[radius],[pdb_id]`

- `name`: The name of the object (required, cannot contain underscores)
- `is_particle`: `True` or `False` indicating if this is a particle (required)
- `radius`: Radius in pixels for particles (optional, only for particles)
- `pdb_id`: PDB ID for the particle structure (optional, only for particles)

**Examples:**

```bash
# Basic filesystem config with membrane and ribosome
copick config filesystem \
    --overlay-root /path/to/project \
    --objects membrane,False \
    --objects ribosome,True,120,4V9D \
    --config my_project.json

# Complex project with multiple particles
copick config filesystem \
    --overlay-root /mnt/data/experiment \
    --objects membrane,False \
    --objects ribosome,True,120,4V9D \
    --objects proteasome,True,80,6MSB \
    --objects apoferritin,True,60,4V1W \
    --proj-name "Cellular_Tomography" \
    --proj-description "Cellular structures from cryo-ET experiment" \
    --config cellular_config.json

# Minimal config
copick config filesystem \
    --overlay-root ./data \
    --objects virus,True,150
```

---

### :material-plus: `copick add`

Add entities to Copick projects.

**Subcommands:**

- [`copick add tomogram`](#copick-add-tomogram) - Add a tomogram to the project

#### :material-cube: `copick add tomogram`

Add one or more tomograms to the project from MRC or Zarr files.

**Usage:**
```bash
copick add tomogram [OPTIONS] PATH
```

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `PATH` | Path | Path to tomogram file(s) (MRC or Zarr format) or glob pattern (e.g., `*.mrc`) |

**Options:**

| Option | Type | Description                                                                                                                  | Default |
|--------|------|------------------------------------------------------------------------------------------------------------------------------|---------|
| `-c, --config PATH` | Path | Path to the configuration file                                                                                               | Uses `COPICK_CONFIG` env var |
| `--run TEXT` | String | The name of the run. If not specified, will use the name of the file (stripping extension), ignored if PATH is glob pattern. | `""` |
| `--tomo-type TEXT` | String | The name of the tomogram (e.g. wbp)                                                                                          | `wbp` |
| `--file-type TEXT` | String | The file type ('mrc' or 'zarr')                                                                                              | Auto-detected |
| `--voxel_size FLOAT` | Float | Voxel size in Angstrom (overrides header value)                                                                              | None |
| `--create-pyramid / --no-create-pyramid` | Boolean | Compute the multiscale pyramid                                                                                               | `create-pyramid` |
| `--pyramid-levels INTEGER` | Integer | Number of pyramid levels (each level is 2x downscaling)                                                                      | `3` |
| `--chunk-size TEXT` | String | Chunk size for the output Zarr file                                                                                          | `256,256,256` |
| `--overwrite / --no-overwrite` | Boolean | Overwrite the object if it exists                                                                                            | `no-overwrite` |
| `--create / --no-create` | Boolean | Create the object if it does not exist                                                                                       | `create` |
| `--debug / --no-debug` | Boolean | Enable debug logging                                                                                                         | `no-debug` |

!!! tip "Batch Processing with Glob Patterns"
    You can add multiple tomograms at once using glob patterns. When using glob patterns, run names are automatically derived from filenames, and a progress bar shows the processing status.

**Examples:**

```bash
# Add single MRC tomogram with default settings
copick add tomogram --config config.json --run TS_001 data/tomogram.mrc

# Add multiple tomograms using glob pattern (auto-detects run names from filenames)
copick add tomogram --config config.json data/tomograms/*.mrc

# Add all MRC files in current directory
copick add tomogram --config config.json *.mrc

# Add tomograms with specific naming pattern
copick add tomogram --config config.json "data/TS_*_recon.mrc"

# Add Zarr tomogram with custom voxel size and pyramid levels
copick add tomogram --config config.json --voxel_size 10.0 --pyramid-levels 4 data/tomogram.zarr

# Add multiple Zarr files without pyramid generation (faster)
copick add tomogram --config config.json --no-create-pyramid data/*.zarr

# Add tomogram with custom chunk size
copick add tomogram --config config.json --chunk-size "128,128,128" data/tomogram.mrc

# Add multiple tomograms with custom settings
copick add tomogram --config config.json --tomo-type "denoised" --voxel_size 8.0 data/processed_*.mrc
```

---

### :material-file-plus: `copick new`

Create new Copick entities.

**Subcommands:**

- [`copick new picks`](#copick-new-picks) - Create empty picks for a given particle name
- [`copick new run`](#copick-new-run) - Create an empty run with the given name
- [`copick new voxelspacing`](#copick-new-voxelspacing) - Create an empty voxelspacing with the given name

#### :material-target: `copick new picks`

Create empty picks for a given particle name.

**Usage:**
```bash
copick new picks [OPTIONS]
```

**Options:**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `-c, --config PATH` | Path | Path to the configuration file | Uses `COPICK_CONFIG` env var |
| `--particle-name TEXT` | String | Name of the particle to create picks for (required) | None |
| `--out-user TEXT` | String | User ID to write picks to | `copick` |
| `--out-session TEXT` | String | Session ID to write picks to | `0` |
| `--overwrite BOOLEAN` | Boolean | Overwrite existing picks | `False` |
| `--debug / --no-debug` | Boolean | Enable debug logging | `no-debug` |

**Examples:**

```bash
# Create empty picks for ribosomes
copick new picks --config config.json --particle-name ribosome

# Create picks with custom user and session
copick new picks --config config.json --particle-name proteasome --out-user alice --out-session 1

# Create picks with overwrite enabled
copick new picks --config config.json --particle-name ribosome --overwrite True
```

#### :material-play: `copick new run`

Create an empty run with the given name.

**Usage:**
```bash
copick new run [OPTIONS] NAME
```

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `NAME` | String | The name of the new run to be created |

**Options:**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `-c, --config PATH` | Path | Path to the configuration file | Uses `COPICK_CONFIG` env var |
| `--overwrite / --no-overwrite` | Boolean | Overwrite the object if it exists | `no-overwrite` |
| `--create / --no-create` | Boolean | Create the object if it does not exist | `create` |
| `--debug / --no-debug` | Boolean | Enable debug logging | `no-debug` |

**Examples:**

```bash
# Create a new run
copick new run --config config.json TS_005

# Create run with overwrite enabled
copick new run --config config.json --overwrite TS_005
```

#### :material-grid: `copick new voxelspacing`

Create an empty voxelspacing with the given name.

**Usage:**
```bash
copick new voxelspacing [OPTIONS] VOXEL_SPACING
```

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `VOXEL_SPACING` | Float | The voxel spacing in Angstrom to be added to the run |

**Options:**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `-c, --config PATH` | Path | Path to the configuration file | Uses `COPICK_CONFIG` env var |
| `--run RUN` | String | Name of the run to add voxel spacing to (required) | None |
| `--overwrite / --no-overwrite` | Boolean | Overwrite the object if it exists | `no-overwrite` |
| `--create / --no-create` | Boolean | Create the object if it does not exist | `create` |
| `--debug / --no-debug` | Boolean | Enable debug logging | `no-debug` |

**Examples:**

```bash
# Add 10.0 Angstrom voxel spacing to run
copick new voxelspacing --config config.json --run TS_001 10.0

# Add voxel spacing with overwrite enabled
copick new voxelspacing --config config.json --run TS_001 --overwrite 5.0
```

---

### :material-information: `copick info`

Display information about the Copick CLI and available plugins.

**Usage:**
```bash
copick info
```

**Examples:**

```bash
# Show CLI information and available plugins
copick info
```

---

## Plugin System

!!! info "Extensibility"
    The Copick CLI supports extensibility through plugins. External packages can register additional commands by defining entry points in the `copick.commands` group.

### Plugin Registration

**Using setup.py:**
```python
from setuptools import setup

setup(
    name="my-copick-plugin",
    entry_points={
        "copick.commands": [
            "my-command = my_package.cli:my_command",
        ],
    },
)
```

**Using pyproject.toml:**
```toml
[project.entry-points."copick.commands"]
my-command = "my_package.cli:my_command"
```

### Plugin Implementation

**Creating a Click Command:**
```python
import click
from copick.cli.util import add_config_option, add_debug_option
from copick.util.log import get_logger

@click.command()
@add_config_option
@add_debug_option
def my_command(config: str, debug: bool):
    """My custom copick command."""
    logger = get_logger(__name__, debug=debug)
    logger.info(f"Running my command with config: {config}")
```

**Usage:**
After installing your package, the command will be available:
```bash
copick my-command --config path/to/config.json
```

---

## Common Workflows

### Setup from Data Portal

Create a new project from CryoET Data Portal datasets:

```bash
# Create configuration from data portal
copick config dataportal --dataset-id 10000 --overlay ./overlay --output project.json

# Set environment variable for convenience
export COPICK_CONFIG=project.json

# Browse the project
copick browse
```

### Add Data to Project

Add tomograms and create annotation templates:

```bash
# Add a single tomogram
copick add tomogram --run TS_001 data/tomogram.mrc

# Add multiple tomograms using glob pattern
copick add tomogram data/tomograms/*.mrc

# Create empty picks for annotation
copick new picks --particle-name ribosome

# Browse to verify
copick browse
```

### Work with Multiple Datasets

Combine multiple datasets in one project:

```bash
# Create configuration with multiple datasets
copick config dataportal -ds 10000 -ds 10001 -ds 10002 --overlay ./overlay --output multi_project.json

# Browse all datasets together
copick browse --config multi_project.json
```

### Development and Debugging

Debug and test your Copick workflows:

```bash
# Run commands with debug logging
copick browse --config project.json --debug

# Create a new run for testing
copick new run --config project.json TEST_RUN

# Add a voxel spacing to the test run
copick new voxelspacing --config project.json --run TEST_RUN 10.0

# Add a tomogram with detailed output
copick add tomogram --config project.json --run TEST_RUN --debug data/test_tomogram.mrc
```
