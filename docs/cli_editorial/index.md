<!-- Editorial content for the CLI Reference landing page. Hand-edit freely;
     `make_cli_docs` never overwrites this file. -->

!!! tip "Environment Variable Support"
    The configuration file path can be set using the `COPICK_CONFIG` environment variable instead of passing `--config` every time:

    ```bash
    export COPICK_CONFIG=/path/to/config.json
    copick browse  # Uses config from environment variable
    ```

## Plugin System

!!! info "Extensibility"
    The Copick CLI supports extensibility through plugins. External packages can register additional commands by defining entry points in multiple supported groups. The `convert`, `process`, `logical`, `training`, `inference`, and `download` command groups are all populated this way (e.g. by `copick-utils` and `copick-torch`).

### Supported Entry Point Groups

- **`copick.commands`**: Commands added directly to the main CLI (e.g., `copick mycommand`)
- **`copick.inference.commands`**: Commands under the inference group (e.g., `copick inference mymodel`)
- **`copick.training.commands`**: Commands under the training group (e.g., `copick training mytrain`)
- **`copick.evaluation.commands`**: Commands under the evaluation group (e.g., `copick evaluation myscore`)
- **`copick.process.commands`**: Commands under the process group (e.g., `copick process mymethod`)
- **`copick.convert.commands`**: Commands under the convert group (e.g., `copick convert myconverter`)
- **`copick.logical.commands`**: Commands under the logical group (e.g., `copick logical myop`)
- **`copick.download.commands`**: Commands under the download group (e.g., `copick download mydata`)

### Plugin Registration

```toml
# Commands added to the main CLI group
[project.entry-points."copick.commands"]
mycommand = "my_copick_plugin.cli.cli:mycommand"

# Commands added to the convert group
[project.entry-points."copick.convert.commands"]
myconverter = "my_copick_plugin.cli.cli:myconverter"
```

### Plugin Implementation

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
```

A complete demo package is available at [copick-plugin-demo](https://github.com/copick/copick-plugin-demo) that demonstrates the project structure, commands for all supported entry point groups, and entry-point configuration. Use it as a template for your own plugins.

### Best Practices

1. **Use descriptive command names** that clearly indicate their purpose.
2. **Follow the existing naming conventions** with hyphens for multi-word commands.
3. **Always use `@add_config_option` and `@add_debug_option`** decorators for consistency.
4. **Add proper docstrings** for your commands — they become the help text and these reference pages.
5. **Use appropriate entry point groups** to organize your commands logically.

## Common Workflows

### Setup from Data Portal

```bash
# Create configuration from data portal
copick config dataportal --dataset-id 10000 --overlay ./overlay --output project.json

# Set environment variable for convenience
export COPICK_CONFIG=project.json

# Browse the project
copick browse
```

### Add Data to a Project

```bash
# Add a single tomogram
copick add tomogram --run TS_001 data/tomogram.mrc

# Add multiple tomograms using a glob pattern
copick add tomogram data/tomograms/*.mrc

# Add pickable objects to the project configuration
copick add object --name ribosome --object-type particle --radius 120 --pdb-id 4V9D --color "255,0,0,255"

# Add segmentation data
copick add segmentation --run TS_001 --name membrane --user-id analyst data/membrane_seg.mrc

# Create empty picks for annotation
copick new picks --particle-name ribosome
```

### Synchronize Data Between Projects

```bash
# Basic synchronization of all data types
copick sync picks -c source_config.json --target-config target_config.json --log
copick sync segmentations -c source_config.json --target-config target_config.json --log

# Sync from CryoET Data Portal to a local project
copick sync picks \
    --source-dataset-ids "12345,67890" \
    --target-config local_project.json \
    --max-workers 8 --log

# Sync with name mapping and user filtering
copick sync picks -c source_config.json --target-config target_config.json \
    --source-runs "run1,run2" --target-runs "run1:experiment_A,run2:experiment_B" \
    --source-objects "ribosome,membrane" --target-objects "ribosome:large_ribosomal_subunit,membrane:plasma_membrane" \
    --exist-ok --log
```

### Import and Export Data

```bash
# Import picks from a RELION STAR file
copick add picks -c project.json --run TS_001 --object-name ribosome \
    --user-id analyst --session-id 1 --voxel-size 10.0 \
    data/particles.star

# Export picks to RELION STAR format for subtomogram averaging
copick export picks -c project.json --picks-uri "ribosome:*/*" \
    --output-dir ./relion_project --output-format star \
    --voxel-size 10.0 --include-optics

# Export tomograms to MRC for external tools
copick export tomogram -c project.json --tomogram-uri "wbp@10.0" \
    --output-dir ./tomograms --output-format mrc
```

### Create a Depositable View for the Data Portal

```bash
# Basic deposit with all picks and meshes from a filesystem project
copick deposit -c project.json --target-dir /path/to/deposit \
    --picks "*:*/*" --meshes "*:*/*"

# Deposit specific data types with filters
copick deposit -c project.json --target-dir /path/to/deposit \
    --picks "ribosome:*/*" --segmentations "membrane:*/*@10.0" \
    --tomograms "wbp@10.0"
```
