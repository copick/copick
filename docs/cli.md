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
- [`copick add segmentation`](#copick-add-segmentation) - Add a segmentation to the project
- [`copick add object`](#copick-add-object) - Add a pickable object to the project configuration
- [`copick add object-volume`](#copick-add-object-volume) - Add volume data to an existing pickable object

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

#### :material-layers: `copick add segmentation`

Add one or more segmentations to the project from MRC or Zarr files.

**Usage:**
```bash
copick add segmentation [OPTIONS] PATH
```

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `PATH` | Path | Path to segmentation file(s) (MRC or Zarr format) or glob pattern (e.g., `*.mrc`) |

**Options:**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `-c, --config PATH` | Path | Path to the configuration file | Uses `COPICK_CONFIG` env var |
| `--run TEXT` | String | The name of the run. If not specified, will use the name of the file (stripping extension), ignored if PATH is glob pattern. | `""` |
| `--voxel-size FLOAT` | Float | Voxel size in Angstrom (overrides header value) | None |
| `--name TEXT` | String | Name of the segmentation | None |
| `--user-id TEXT` | String | User ID of the segmentation | `copick` |
| `--session-id TEXT` | String | Session ID of the segmentation | `1` |
| `--overwrite / --no-overwrite` | Boolean | Overwrite the object if it exists | `no-overwrite` |
| `--create / --no-create` | Boolean | Create the object if it does not exist | `create` |
| `--debug / --no-debug` | Boolean | Enable debug logging | `no-debug` |

**Examples:**

```bash
# Add single segmentation with default settings
copick add segmentation --config config.json --run TS_001 --name membrane data/segmentation.mrc

# Add multiple segmentations using glob pattern
copick add segmentation --config config.json --name organelles data/segmentations/*.mrc

# Add segmentation with custom user and session
copick add segmentation --config config.json --run TS_001 --name mitochondria --user-id alice --session-id 2 data/mito_seg.mrc

# Add segmentation with custom voxel size
copick add segmentation --config config.json --run TS_001 --name membrane --voxel-size 10.0 data/membrane.zarr
```

#### :material-shape: `copick add object`

Add a pickable object to the project configuration.

**Usage:**
```bash
copick add object [OPTIONS]
```

**Options:**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `-c, --config PATH` | Path | Path to the configuration file | Uses `COPICK_CONFIG` env var |
| `--name TEXT` | String | Name of the object to add (required) | None |
| `--object-type CHOICE` | String | Type of object: 'particle' or 'segmentation' | `particle` |
| `--label INTEGER` | Integer | Numeric label/id for the object. If not provided, will use the next available label | None |
| `--color TEXT` | String | RGBA color for the object as comma-separated values (e.g. '255,0,0,255' for red) | None |
| `--emdb-id TEXT` | String | EMDB ID for the object | None |
| `--pdb-id TEXT` | String | PDB ID for the object | None |
| `--identifier TEXT` | String | Identifier for the object (e.g. Gene Ontology ID or UniProtKB accession) | None |
| `--map-threshold FLOAT` | Float | Threshold to apply to the map when rendering the isosurface | None |
| `--radius FLOAT` | Float | Radius of the particle, when displaying as a sphere | `50` |
| `--volume PATH` | Path | Path to volume file to associate with the object | None |
| `--volume-format CHOICE` | String | Format of the volume file ('mrc' or 'zarr') | Auto-detected |
| `--voxel-size FLOAT` | Float | Voxel size for the volume data. Required if volume is provided | None |
| `--exist-ok / --no-exist-ok` | Boolean | Whether existing objects with the same name should be overwritten | `no-exist-ok` |
| `--debug / --no-debug` | Boolean | Enable debug logging | `no-debug` |

**Examples:**

```bash
# Add a basic particle object
copick add object --config config.json --name ribosome --object-type particle --radius 120

# Add a particle with PDB reference and custom color
copick add object --config config.json --name ribosome --object-type particle --radius 120 --pdb-id 4V9D --color "255,0,0,255"

# Add a segmentation object with custom label
copick add object --config config.json --name membrane --object-type segmentation --label 1 --color "0,255,0,128"

# Add a particle with associated volume data
copick add object --config config.json --name proteasome --object-type particle --radius 80 --volume data/proteasome.mrc --voxel-size 10.0

# Add object with EMDB reference and identifier
copick add object --config config.json --name apoferritin --object-type particle --emdb-id EMD-1234 --identifier "GO:0006826" --radius 60
```

#### :material-cube-outline: `copick add object-volume`

Add volume data to an existing pickable object.

**Usage:**
```bash
copick add object-volume [OPTIONS]
```

**Options:**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `-c, --config PATH` | Path | Path to the configuration file | Uses `COPICK_CONFIG` env var |
| `--object-name TEXT` | String | Name of the existing object (required) | None |
| `--volume-path PATH` | Path | Path to the volume file (required) | None |
| `--volume-format CHOICE` | String | Format of the volume file ('mrc' or 'zarr') | Auto-detected |
| `--voxel-size FLOAT` | Float | Voxel size of the volume data in Angstrom | None |
| `--debug / --no-debug` | Boolean | Enable debug logging | `no-debug` |

**Examples:**

```bash
# Add volume data to an existing object
copick add object-volume --config config.json --object-name ribosome --volume-path data/ribosome_volume.mrc

# Add volume with custom voxel size
copick add object-volume --config config.json --object-name proteasome --volume-path data/proteasome.zarr --voxel-size 8.0

# Add volume with explicit format specification
copick add object-volume --config config.json --object-name membrane --volume-path data/membrane_vol --volume-format zarr
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
    The Copick CLI supports extensibility through plugins. External packages can register additional commands by defining entry points in multiple supported groups.

### Supported Entry Point Groups

The plugin system supports the following entry point groups:

- **`copick.commands`**: Commands added directly to the main CLI (e.g., `copick mycommand`)
- **`copick.inference.commands`**: Commands under the inference group (e.g., `copick inference mymodel`)
- **`copick.training.commands`**: Commands under the training group (e.g., `copick training mytrain`)
- **`copick.evaluation.commands`**: Commands under the evaluation group (e.g., `copick evaluation myscore`)
- **`copick.process.commands`**: Commands under the process group (e.g., `copick process mymethod`)
- **`copick.convert.commands`**: Commands under the convert group (e.g., `copick convert myconverter`)

### Plugin Registration

**Using pyproject.toml:**
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

### Plugin Implementation

**Creating Click Commands:**
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

@click.command(short_help="A training command.")
@add_config_option
@click.option("--epochs", type=int, default=100, help="Number of training epochs.")
@add_debug_option
@click.pass_context
def mymodel_train(ctx: click.Context, config: str, epochs: int, debug: bool):
    """A command that serves as an example for how to implement a training CLI command in copick."""
    logger = get_logger(__name__, debug=debug)
    logger.info(f"Starting training for {epochs} epochs")
    # Add your training logic here
```

### Demo Package

A complete demo package is available at [copick-plugin-demo](https://github.com/copick/copick-plugin-demo) that demonstrates:

- Project structure for copick plugins
- Commands for all supported entry point groups
- Proper use of copick utilities like `add_config_option` and `add_debug_option`
- Entry point configuration in `pyproject.toml`
- Example command implementations

You can use this demo as a template for creating your own copick plugins.

### Usage

After installing your package, the commands will be available:
```bash
# Main CLI commands
copick mycommand --config path/to/config.json --option value

# Grouped commands
copick inference mymodel-infer --config path/to/config.json --model-path ./model.pt
copick training mymodel-train --config path/to/config.json --epochs 50
copick evaluation myscore --config path/to/config.json
copick process mymethod --config path/to/config.json
copick convert myconverter --config path/to/config.json
```

### Best Practices

1. **Use descriptive command names** that clearly indicate their purpose
2. **Follow the existing naming conventions** with hyphens for multi-word commands
3. **Always use `@add_config_option` and `@add_debug_option`** decorators for consistency
4. **Add proper docstrings** for your commands - they become the help text
5. **Use appropriate entry point groups** to organize your commands logically
6. **Test your plugins** with the demo package structure as a reference

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

Add tomograms, segmentations, and objects to your project:

```bash
# Add a single tomogram
copick add tomogram --run TS_001 data/tomogram.mrc

# Add multiple tomograms using glob pattern
copick add tomogram data/tomograms/*.mrc

# Add pickable objects to the project configuration
copick add object --name ribosome --object-type particle --radius 120 --pdb-id 4V9D --color "255,0,0,255"
copick add object --name membrane --object-type segmentation --label 1 --color "0,255,0,128"

# Add volume data to existing objects
copick add object-volume --object-name ribosome --volume-path data/ribosome_reference.mrc --voxel-size 10.0

# Add segmentation data
copick add segmentation --run TS_001 --name membrane --user-id analyst data/membrane_seg.mrc

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
