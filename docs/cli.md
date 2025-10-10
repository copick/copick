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

| Option                  | Type    | Description                                       | Default                      |
|-------------------------|---------|---------------------------------------------------|------------------------------|
| `-c, --config PATH`     | Path    | Path to the configuration file                    | Uses `COPICK_CONFIG` env var |
| `-ds, --dataset-ids ID` | Integer | Dataset IDs to include (multiple inputs possible) | None                         |
| `--debug / --no-debug`  | Boolean | Enable debug logging                              | `no-debug`                   |

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

| Option                      | Type    | Description                                                          | Default       |
|-----------------------------|---------|----------------------------------------------------------------------|---------------|
| `-ds, --dataset-id INTEGER` | Integer | Dataset IDs from the CryoET Data Portal (required, multiple allowed) | None          |
| `--overlay TEXT`            | Path    | Path to the local overlay directory (required)                       | None          |
| `--output TEXT`             | Path    | Path to save the generated configuration file                        | `config.json` |
| `--debug / --no-debug`      | Boolean | Enable debug logging                                                 | `no-debug`    |

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

| Option                    | Type    | Description                                                                                              | Default                         |
|---------------------------|---------|----------------------------------------------------------------------------------------------------------|---------------------------------|
| `--overlay-root TEXT`     | Path    | Overlay root path (required)                                                                             | None                            |
| `--objects TEXT`          | String  | List of desired objects in the format: `name,is_particle,[radius],[pdb_id]` (required, multiple allowed) | None                            |
| `--config TEXT`           | Path    | Path to the output JSON configuration file                                                               | `config.json`                   |
| `--proj-name TEXT`        | String  | Name of the project configuration                                                                        | `project`                       |
| `--proj-description TEXT` | String  | Description of the project configuration                                                                 | `Config Project for SessionXXa` |
| `--debug / --no-debug`    | Boolean | Enable debug logging                                                                                     | `no-debug`                      |

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

| Argument | Type | Description                                                                   |
|----------|------|-------------------------------------------------------------------------------|
| `PATH`   | Path | Path to tomogram file(s) (MRC or Zarr format) or glob pattern (e.g., `*.mrc`) |

**Options:**

| Option                                   | Type    | Description                                                                                                                  | Default                      |
|------------------------------------------|---------|------------------------------------------------------------------------------------------------------------------------------|------------------------------|
| `-c, --config PATH`                      | Path    | Path to the configuration file                                                                                               | Uses `COPICK_CONFIG` env var |
| `--run TEXT`                             | String  | The name of the run. If not specified, will use the name of the file (stripping extension), ignored if PATH is glob pattern. | `""`                         |
| `--run-regex TEXT`                       | String  | Regular expression to extract the run name from the filename. The regex should capture the run name in the first group.      | `(.*)`                       |
| `--tomo-type TEXT`                       | String  | The name of the tomogram (e.g. wbp)                                                                                          | `wbp`                        |
| `--file-type TEXT`                       | String  | The file type ('mrc' or 'zarr')                                                                                              | Auto-detected                |
| `--voxel_size FLOAT`                     | Float   | Voxel size in Angstrom (overrides header value)                                                                              | None                         |
| `--create-pyramid / --no-create-pyramid` | Boolean | Compute the multiscale pyramid                                                                                               | `create-pyramid`             |
| `--pyramid-levels INTEGER`               | Integer | Number of pyramid levels (each level is 2x downscaling)                                                                      | `3`                          |
| `--chunk-size TEXT`                      | String  | Chunk size for the output Zarr file                                                                                          | `256,256,256`                |
| `--overwrite / --no-overwrite`           | Boolean | Overwrite the object if it exists                                                                                            | `no-overwrite`               |
| `--create / --no-create`                 | Boolean | Create the object if it does not exist                                                                                       | `create`                     |
| `--debug / --no-debug`                   | Boolean | Enable debug logging                                                                                                         | `no-debug`                   |

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

# Extract run names using regex pattern
# For file "Position_60_7_Vol_CTF.mrc", this will create run "Position_60_7"
copick add tomogram --config config.json --run-regex "^(Position_.*)_Vol_CTF" data/Position_60_7_Vol_CTF.mrc

# Use regex with glob pattern for multiple files with structured naming
copick add tomogram --config config.json --run-regex "^(Position_.*)_Vol_CTF" data/Position_*_Vol_CTF.mrc
```

#### :material-layers: `copick add segmentation`

Add one or more segmentations to the project from MRC or Zarr files.

**Usage:**
```bash
copick add segmentation [OPTIONS] PATH
```

**Arguments:**

| Argument | Type | Description                                                                       |
|----------|------|-----------------------------------------------------------------------------------|
| `PATH`   | Path | Path to segmentation file(s) (MRC or Zarr format) or glob pattern (e.g., `*.mrc`) |

**Options:**

| Option                         | Type    | Description                                                                                                                  | Default                      |
|--------------------------------|---------|------------------------------------------------------------------------------------------------------------------------------|------------------------------|
| `-c, --config PATH`            | Path    | Path to the configuration file                                                                                               | Uses `COPICK_CONFIG` env var |
| `--run TEXT`                   | String  | The name of the run. If not specified, will use the name of the file (stripping extension), ignored if PATH is glob pattern. | `""`                         |
| `--run-regex TEXT`             | String  | Regular expression to extract the run name from the filename. The regex should capture the run name in the first group.      | `(.*)`                       |
| `--voxel-size FLOAT`           | Float   | Voxel size in Angstrom (overrides header value)                                                                              | None                         |
| `--name TEXT`                  | String  | Name of the segmentation                                                                                                     | None                         |
| `--user-id TEXT`               | String  | User ID of the segmentation                                                                                                  | `copick`                     |
| `--session-id TEXT`            | String  | Session ID of the segmentation                                                                                               | `1`                          |
| `--overwrite / --no-overwrite` | Boolean | Overwrite the object if it exists                                                                                            | `no-overwrite`               |
| `--create / --no-create`       | Boolean | Create the object if it does not exist                                                                                       | `create`                     |
| `--debug / --no-debug`         | Boolean | Enable debug logging                                                                                                         | `no-debug`                   |

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

# Extract run names using regex pattern for segmentations
# For file "Position_60_7_Vol_CTF.mrc", this will create run "Position_60_7"
copick add segmentation --config config.json --run-regex "^(Position_.*)_Vol_CTF" --name membrane data/Position_60_7_Vol_CTF.mrc
```

#### :material-shape: `copick add object`

Add a pickable object to the project configuration.

**Usage:**
```bash
copick add object [OPTIONS]
```

**Options:**

| Option                       | Type    | Description                                                                         | Default                      |
|------------------------------|---------|-------------------------------------------------------------------------------------|------------------------------|
| `-c, --config PATH`          | Path    | Path to the configuration file                                                      | Uses `COPICK_CONFIG` env var |
| `--name TEXT`                | String  | Name of the object to add (required)                                                | None                         |
| `--object-type CHOICE`       | String  | Type of object: 'particle' or 'segmentation'                                        | `particle`                   |
| `--label INTEGER`            | Integer | Numeric label/id for the object. If not provided, will use the next available label | None                         |
| `--color TEXT`               | String  | RGBA color for the object as comma-separated values (e.g. '255,0,0,255' for red)    | None                         |
| `--emdb-id TEXT`             | String  | EMDB ID for the object                                                              | None                         |
| `--pdb-id TEXT`              | String  | PDB ID for the object                                                               | None                         |
| `--identifier TEXT`          | String  | Identifier for the object (e.g. Gene Ontology ID or UniProtKB accession)            | None                         |
| `--map-threshold FLOAT`      | Float   | Threshold to apply to the map when rendering the isosurface                         | None                         |
| `--radius FLOAT`             | Float   | Radius of the particle, when displaying as a sphere                                 | `50`                         |
| `--metadata TEXT`            | String  | JSON string containing custom metadata for the object (e.g. '{"source": "experimental_data", "confidence": 0.95}') | None |
| `--volume PATH`              | Path    | Path to volume file to associate with the object                                    | None                         |
| `--volume-format CHOICE`     | String  | Format of the volume file ('mrc' or 'zarr')                                         | Auto-detected                |
| `--voxel-size FLOAT`         | Float   | Voxel size for the volume data. Required if volume is provided                      | None                         |
| `--exist-ok / --no-exist-ok` | Boolean | Whether existing objects with the same name should be overwritten                   | `no-exist-ok`                |
| `--debug / --no-debug`       | Boolean | Enable debug logging                                                                | `no-debug`                   |

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

# Add object with custom metadata
copick add object --config config.json --name ribosome --object-type particle --radius 120 --metadata '{"source": "experimental_data", "confidence": 0.95, "notes": "High-resolution structure"}'
```

#### :material-cube-outline: `copick add object-volume`

Add volume data to an existing pickable object.

**Usage:**
```bash
copick add object-volume [OPTIONS]
```

**Options:**

| Option                   | Type    | Description                                 | Default                      |
|--------------------------|---------|---------------------------------------------|------------------------------|
| `-c, --config PATH`      | Path    | Path to the configuration file              | Uses `COPICK_CONFIG` env var |
| `--object-name TEXT`     | String  | Name of the existing object (required)      | None                         |
| `--volume-path PATH`     | Path    | Path to the volume file (required)          | None                         |
| `--volume-format CHOICE` | String  | Format of the volume file ('mrc' or 'zarr') | Auto-detected                |
| `--voxel-size FLOAT`     | Float   | Voxel size of the volume data in Angstrom   | None                         |
| `--debug / --no-debug`   | Boolean | Enable debug logging                        | `no-debug`                   |

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

| Option                 | Type    | Description                                         | Default                      |
|------------------------|---------|-----------------------------------------------------|------------------------------|
| `-c, --config PATH`    | Path    | Path to the configuration file                      | Uses `COPICK_CONFIG` env var |
| `--particle-name TEXT` | String  | Name of the particle to create picks for (required) | None                         |
| `--out-user TEXT`      | String  | User ID to write picks to                           | `copick`                     |
| `--out-session TEXT`   | String  | Session ID to write picks to                        | `0`                          |
| `--overwrite BOOLEAN`  | Boolean | Overwrite existing picks                            | `False`                      |
| `--debug / --no-debug` | Boolean | Enable debug logging                                | `no-debug`                   |

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

| Argument | Type   | Description                           |
|----------|--------|---------------------------------------|
| `NAME`   | String | The name of the new run to be created |

**Options:**

| Option                         | Type    | Description                            | Default                      |
|--------------------------------|---------|----------------------------------------|------------------------------|
| `-c, --config PATH`            | Path    | Path to the configuration file         | Uses `COPICK_CONFIG` env var |
| `--overwrite / --no-overwrite` | Boolean | Overwrite the object if it exists      | `no-overwrite`               |
| `--create / --no-create`       | Boolean | Create the object if it does not exist | `create`                     |
| `--debug / --no-debug`         | Boolean | Enable debug logging                   | `no-debug`                   |

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

| Argument        | Type  | Description                                          |
|-----------------|-------|------------------------------------------------------|
| `VOXEL_SPACING` | Float | The voxel spacing in Angstrom to be added to the run |

**Options:**

| Option                         | Type    | Description                                        | Default                      |
|--------------------------------|---------|----------------------------------------------------|------------------------------|
| `-c, --config PATH`            | Path    | Path to the configuration file                     | Uses `COPICK_CONFIG` env var |
| `--run RUN`                    | String  | Name of the run to add voxel spacing to (required) | None                         |
| `--overwrite / --no-overwrite` | Boolean | Overwrite the object if it exists                  | `no-overwrite`               |
| `--create / --no-create`       | Boolean | Create the object if it does not exist             | `create`                     |
| `--debug / --no-debug`         | Boolean | Enable debug logging                               | `no-debug`                   |

**Examples:**

```bash
# Add 10.0 Angstrom voxel spacing to run
copick new voxelspacing --config config.json --run TS_001 10.0

# Add voxel spacing with overwrite enabled
copick new voxelspacing --config config.json --run TS_001 --overwrite 5.0
```

---

### :material-sync: `copick sync`

Synchronize data between Copick projects with support for parallel processing, name mapping, and user filtering.

**Subcommands:**

- [`copick sync picks`](#copick-sync-picks) - Synchronize picks between two Copick projects
- [`copick sync meshes`](#copick-sync-meshes) - Synchronize meshes between two Copick projects
- [`copick sync segmentations`](#copick-sync-segmentations) - Synchronize segmentations between two Copick projects
- [`copick sync tomograms`](#copick-sync-tomograms) - Synchronize tomograms between two Copick projects

#### :material-target: `copick sync picks`

Synchronize pick annotations between two Copick projects with support for name mapping and user filtering.

**Usage:**
```bash
copick sync picks [OPTIONS]
```

**Options:**

| Option                    | Type    | Description                                                                                             | Default                      |
|---------------------------|---------|---------------------------------------------------------------------------------------------------------|------------------------------|
| `-c, --config PATH`       | Path    | Path to the source configuration file                                                                   | Uses `COPICK_CONFIG` env var |
| `--source-dataset-ids`    | String  | Comma-separated list of dataset IDs to use as source from CryoET Data Portal                           | `""`                         |
| `--target-config PATH`    | Path    | Path to the target configuration file (required)                                                       | None                         |
| `--source-runs`           | String  | Comma-separated list of source run names to synchronize                                                | `""` (all runs)              |
| `--target-runs`           | String  | Comma-separated mapping of source run names to target run names (e.g. 'run1:target1,run2:target2')    | `""` (same names)            |
| `--source-objects`        | String  | Comma-separated list of source object names to synchronize                                             | `""` (all objects)           |
| `--target-objects`        | String  | Comma-separated mapping of source object names to target object names (e.g. 'ribosome:ribo,membrane:mem') | `""` (same names)            |
| `--source-users`          | String  | Comma-separated list of source user IDs to synchronize                                                 | `""` (all users)             |
| `--target-users`          | String  | Comma-separated mapping of source user IDs to target user IDs (e.g. 'user1:target1,user2:target2')    | `""` (same user IDs)         |
| `--exist-ok/--no-exist-ok` | Boolean | Allow overwriting existing picks in the target project                                                 | `no-exist-ok`                |
| `--max-workers`           | Integer | Maximum number of worker threads to use for synchronization                                            | `4`                          |
| `--log/--no-log`          | Boolean | Enable verbose logging of the synchronization process                                                  | `no-log`                     |
| `--debug/--no-debug`      | Boolean | Enable debug logging                                                                                   | `no-debug`                   |

**Examples:**

```bash
# Sync all picks from all runs
copick sync picks -c source_config.json --target-config target_config.json

# Sync specific runs with name mapping
copick sync picks -c source_config.json --target-config target_config.json \
    --source-runs "run1,run2" --target-runs "run1:new_run1,run2:new_run2"

# Sync specific objects with name mapping
copick sync picks -c source_config.json --target-config target_config.json \
    --source-objects "ribosome,membrane" --target-objects "ribosome:ribo,membrane:mem"

# Sync picks from specific users with user mapping
copick sync picks -c source_config.json --target-config target_config.json \
    --source-users "user1,user2" --target-users "user1:analyst1,user2:analyst2" \
    --exist-ok --log

# Sync from CryoET Data Portal to local project
copick sync picks \
    --source-dataset-ids "12345,67890" \
    --target-config target_config.json \
    --max-workers 8 --log
```

#### :material-vector-triangle: `copick sync meshes`

Synchronize mesh data between two Copick projects with support for name mapping and user filtering.

**Usage:**
```bash
copick sync meshes [OPTIONS]
```

**Options:**

| Option                    | Type    | Description                                                                                             | Default                      |
|---------------------------|---------|---------------------------------------------------------------------------------------------------------|------------------------------|
| `-c, --config PATH`       | Path    | Path to the source configuration file                                                                   | Uses `COPICK_CONFIG` env var |
| `--source-dataset-ids`    | String  | Comma-separated list of dataset IDs to use as source from CryoET Data Portal                           | `""`                         |
| `--target-config PATH`    | Path    | Path to the target configuration file (required)                                                       | None                         |
| `--source-runs`           | String  | Comma-separated list of source run names to synchronize                                                | `""` (all runs)              |
| `--target-runs`           | String  | Comma-separated mapping of source run names to target run names (e.g. 'run1:target1,run2:target2')    | `""` (same names)            |
| `--source-objects`        | String  | Comma-separated list of source object names to synchronize                                             | `""` (all objects)           |
| `--target-objects`        | String  | Comma-separated mapping of source object names to target object names (e.g. 'ribosome:ribo,membrane:mem') | `""` (same names)            |
| `--source-users`          | String  | Comma-separated list of source user IDs to synchronize                                                 | `""` (all users)             |
| `--target-users`          | String  | Comma-separated mapping of source user IDs to target user IDs (e.g. 'user1:target1,user2:target2')    | `""` (same user IDs)         |
| `--exist-ok/--no-exist-ok` | Boolean | Allow overwriting existing meshes in the target project                                                | `no-exist-ok`                |
| `--max-workers`           | Integer | Maximum number of worker threads to use for synchronization                                            | `4`                          |
| `--log/--no-log`          | Boolean | Enable verbose logging of the synchronization process                                                  | `no-log`                     |
| `--debug/--no-debug`      | Boolean | Enable debug logging                                                                                   | `no-debug`                   |

**Examples:**

```bash
# Sync all meshes from all runs
copick sync meshes -c source_config.json --target-config target_config.json

# Sync specific runs with name mapping
copick sync meshes -c source_config.json --target-config target_config.json \
    --source-runs "run1,run2" --target-runs "run1:new_run1,run2:new_run2"

# Sync specific objects with name mapping
copick sync meshes -c source_config.json --target-config target_config.json \
    --source-objects "ribosome,membrane" --target-objects "ribosome:ribo,membrane:mem"

# Parallel processing with logging
copick sync meshes -c source_config.json --target-config target_config.json \
    --max-workers 8 --log
```

#### :material-layers: `copick sync segmentations`

Synchronize segmentation data between two Copick projects with voxel spacing filtering, name mapping, and user filtering.

**Usage:**
```bash
copick sync segmentations [OPTIONS]
```

**Options:**

| Option                    | Type    | Description                                                                                             | Default                      |
|---------------------------|---------|---------------------------------------------------------------------------------------------------------|------------------------------|
| `-c, --config PATH`       | Path    | Path to the source configuration file                                                                   | Uses `COPICK_CONFIG` env var |
| `--source-dataset-ids`    | String  | Comma-separated list of dataset IDs to use as source from CryoET Data Portal                           | `""`                         |
| `--target-config PATH`    | Path    | Path to the target configuration file (required)                                                       | None                         |
| `--source-runs`           | String  | Comma-separated list of source run names to synchronize                                                | `""` (all runs)              |
| `--target-runs`           | String  | Comma-separated mapping of source run names to target run names (e.g. 'run1:target1,run2:target2')    | `""` (same names)            |
| `--voxel-spacings`        | String  | Comma-separated list of voxel spacings to consider for synchronization                                 | `""` (all voxel spacings)    |
| `--source-names`          | String  | Comma-separated list of source segmentation names to synchronize                                       | `""` (all segmentations)     |
| `--target-names`          | String  | Comma-separated mapping of source segmentation names to target names (e.g. 'seg1:target1,seg2:target2') | `""` (same names)            |
| `--source-users`          | String  | Comma-separated list of source user IDs to synchronize                                                 | `""` (all users)             |
| `--target-users`          | String  | Comma-separated mapping of source user IDs to target user IDs (e.g. 'user1:target1,user2:target2')    | `""` (same user IDs)         |
| `--exist-ok/--no-exist-ok` | Boolean | Allow overwriting existing segmentations in the target project                                         | `no-exist-ok`                |
| `--max-workers`           | Integer | Maximum number of worker threads to use for synchronization                                            | `4`                          |
| `--log/--no-log`          | Boolean | Enable verbose logging of the synchronization process                                                  | `no-log`                     |
| `--debug/--no-debug`      | Boolean | Enable debug logging                                                                                   | `no-debug`                   |

**Examples:**

```bash
# Sync all segmentations from all runs
copick sync segmentations -c source_config.json --target-config target_config.json

# Sync specific runs and voxel spacings
copick sync segmentations -c source_config.json --target-config target_config.json \
    --source-runs "run1,run2" --voxel-spacings "10.0,20.0"

# Sync specific segmentations with name mapping
copick sync segmentations -c source_config.json --target-config target_config.json \
    --source-names "membrane,organelle" --target-names "membrane:cell_membrane,organelle:mitochondria"

# Complete synchronization with all options
copick sync segmentations -c source_config.json --target-config target_config.json \
    --source-runs "run1,run2" --target-runs "run1:exp1,run2:exp2" \
    --voxel-spacings "10.0,20.0" \
    --source-names "membrane,organelle" --target-names "membrane:cell_membrane,organelle:mitochondria" \
    --source-users "user1,user2" --target-users "user1:analyst1,user2:analyst2" \
    --exist-ok --max-workers 8 --log
```

#### :material-cube: `copick sync tomograms`

Synchronize tomogram data between two Copick projects with voxel spacing and tomogram type filtering.

**Usage:**
```bash
copick sync tomograms [OPTIONS]
```

**Options:**

| Option                    | Type    | Description                                                                                             | Default                      |
|---------------------------|---------|---------------------------------------------------------------------------------------------------------|------------------------------|
| `-c, --config PATH`       | Path    | Path to the source configuration file                                                                   | Uses `COPICK_CONFIG` env var |
| `--source-dataset-ids`    | String  | Comma-separated list of dataset IDs to use as source from CryoET Data Portal                           | `""`                         |
| `--target-config PATH`    | Path    | Path to the target configuration file (required)                                                       | None                         |
| `--source-runs`           | String  | Comma-separated list of source run names to synchronize                                                | `""` (all runs)              |
| `--target-runs`           | String  | Comma-separated mapping of source run names to target run names (e.g. 'run1:target1,run2:target2')    | `""` (same names)            |
| `--voxel-spacings`        | String  | Comma-separated list of voxel spacings to consider for synchronization                                 | `""` (all voxel spacings)    |
| `--source-tomo-types`     | String  | Comma-separated list of source tomogram types to synchronize                                           | `""` (all tomogram types)    |
| `--target-tomo-types`     | String  | Comma-separated mapping of source tomogram types to target types (e.g. 'wbp:filtered,raw:original')   | `""` (same types)            |
| `--exist-ok/--no-exist-ok` | Boolean | Allow overwriting existing tomograms in the target project                                             | `no-exist-ok`                |
| `--max-workers`           | Integer | Maximum number of worker threads to use for synchronization                                            | `4`                          |
| `--log/--no-log`          | Boolean | Enable verbose logging of the synchronization process                                                  | `no-log`                     |
| `--debug/--no-debug`      | Boolean | Enable debug logging                                                                                   | `no-debug`                   |

**Examples:**

```bash
# Sync all tomograms from all runs
copick sync tomograms -c source_config.json --target-config target_config.json

# Sync specific runs and voxel spacings
copick sync tomograms -c source_config.json --target-config target_config.json \
    --source-runs "run1,run2" --voxel-spacings "10.0,20.0"

# Sync specific tomogram types with name mapping
copick sync tomograms -c source_config.json --target-config target_config.json \
    --source-tomo-types "wbp,raw" --target-tomo-types "wbp:filtered,raw:original"

# Complete tomogram synchronization
copick sync tomograms -c source_config.json --target-config target_config.json \
    --source-runs "run1,run2" --target-runs "run1:exp1,run2:exp2" \
    --voxel-spacings "10.0" \
    --source-tomo-types "wbp,denoised" --target-tomo-types "wbp:processed,denoised:clean" \
    --exist-ok --max-workers 6 --log
```

---

### :material-folder-arrow-right: `copick deposit`

Create a depositable view of a copick project using symlinks.

This command creates a hierarchical directory structure suitable for uploading to the cryoET data portal. It operates on a single copick config and creates symlinks to the actual data files, allowing multiple projects to be deposited into the same target directory through successive executions.

**Usage:**
```bash
copick deposit [OPTIONS]
```

**Options:**

| Option                  | Type    | Description                                                                                                                                                      | Default                      |
|-------------------------|---------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------|
| `-c, --config PATH`     | Path    | Path to the configuration file                                                                                                                                   | Uses `COPICK_CONFIG` env var |
| `--target-dir PATH`     | Path    | Target directory for the deposited view (required)                                                                                                               | None                         |
| `--run-names TEXT`      | String  | Comma-separated list of specific run names to process. If not specified, processes all runs                                                                      | `""` (all runs)              |
| `--run-name-prefix TEXT`| String  | Prefix to prepend to all run names. For data portal projects, if not provided, automatically constructs `{dataset_id}_{portal_run_name}_` for each run          | `""`                         |
| `--run-name-regex TEXT` | String  | Optional regex to define how to extract run names from copick run names. Run names will be extracted from the first group defined using parentheses             | None                         |
| `--picks TEXT`          | String  | URIs to filter picks (e.g., `proteasome:*/*` or `ribosome:user1/*`). Can be specified multiple times. If not specified, skips picks entirely                    | None                         |
| `--meshes TEXT`         | String  | URIs to filter meshes. Can be specified multiple times. If not specified, skips meshes entirely                                                                 | None                         |
| `--segmentations TEXT`  | String  | URIs to filter segmentations (e.g., `membrane:*/*@10.0`). Can be specified multiple times. If not specified, skips segmentations entirely                       | None                         |
| `--tomograms TEXT`      | String  | URIs to filter tomograms (e.g., `wbp@10.0`). Can be specified multiple times. If not specified, skips tomograms entirely                                        | None                         |
| `--features TEXT`       | String  | URIs to filter features (e.g., `wbp@10.0:cellcanvas`). Can be specified multiple times. If not specified, skips features entirely                               | None                         |
| `--max-workers INTEGER` | Integer | Number of parallel workers for processing runs                                                                                                                   | `8`                          |
| `--debug / --no-debug`  | Boolean | Enable debug logging                                                                                                                                             | `no-debug`                   |

**Examples:**

```bash
# Deposit all runs from a filesystem project with all picks and meshes
copick deposit -c filesystem_config.json --target-dir /path/to/deposit \
    --picks "*:*/*" --meshes "*:*/*"

# Deposit from a data portal project (automatic run name transformation)
# Runs will be named like: 10301_TS_001_<portal_run_id>
copick deposit -c portal_config.json --target-dir /path/to/deposit \
    --picks "proteasome:*/*" --picks "ribosome:*/*" \
    --segmentations "membrane:*/*@10.0"

# Deposit specific runs with explicit prefix override
copick deposit -c config.json --target-dir /path/to/deposit \
    --run-names "TS_001,TS_002" --run-name-prefix "custom_prefix_" \
    --picks "*:*/*"

# Deposit with regex to extract run names
# For runs named "TS_001_processed", this extracts "TS_001"
copick deposit -c config.json --target-dir /path/to/deposit \
    --run-name-regex "^(TS_\d+).*" --tomograms "wbp@10.0"

# Deposit specific data types with filters
copick deposit -c config.json --target-dir /path/to/deposit \
    --picks "proteasome:*/*" --picks "ribosome:analyst1/*" \
    --segmentations "membrane:*/*@10.0" --segmentations "organelle:*/*@10.0" \
    --tomograms "wbp@10.0" --tomograms "denoised@10.0"

# Multiple projects to same target (successive executions)
copick deposit -c project1.json --target-dir /deposit --run-name-prefix "proj1_" \
    --picks "*:*/*"
copick deposit -c project2.json --target-dir /deposit --run-name-prefix "proj2_" \
    --picks "*:*/*"

# Complex deposit with multiple filters and settings
copick deposit -c config.json --target-dir /path/to/deposit \
    --run-names "TS_001,TS_002,TS_003" \
    --picks "proteasome:*/*" --picks "ribosome:*/*" \
    --meshes "membrane:*/*" \
    --segmentations "membrane:*/*@10.0" \
    --tomograms "wbp@10.0" \
    --features "wbp@10.0:cellcanvas" \
    --max-workers 16
```

!!! info "URI Syntax"
    The deposit command uses URI patterns to filter which data to include:

    - **Picks/Meshes**: `object_name:user_id/session_id` (e.g., `ribosome:user1/*` or `*:*/*` for all)
    - **Segmentations**: `name:user_id/session_id@voxel_size` (e.g., `membrane:*/*@10.0`)
    - **Tomograms**: `tomo_type@voxel_size` (e.g., `wbp@10.0`)
    - **Features**: `tomo_type@voxel_size:feature_type` (e.g., `wbp@10.0:cellcanvas`)

    Use `*` as a wildcard to match all values in that position.

!!! tip "Data Portal Projects"
    For data portal projects, run names are automatically transformed from portal run IDs to `{dataset_id}_{portal_run_name}_{portal_run_id}` unless `--run-name-prefix` is explicitly provided. This ensures unique run names when depositing multiple datasets.

!!! warning "Important Notes"
    - Multiple executions to the same `target-dir` are safe and idempotent
    - Symlinks that already exist and point to the correct source are skipped
    - Read-only data from the portal cannot be symlinked and will raise an error
    - Data must be in the overlay (writable) to be deposited

---

### :material-chart-bar: `copick stats`

Gather statistics about a Copick project's entities including picks, meshes, and segmentations.

**Subcommands:**

- [`copick stats picks`](#copick-stats-picks) - Generate statistics for picks in the project
- [`copick stats meshes`](#copick-stats-meshes) - Generate statistics for meshes in the project
- [`copick stats segmentations`](#copick-stats-segmentations) - Generate statistics for segmentations in the project

#### :material-target: `copick stats picks`

Generate comprehensive statistics for picks including total counts and distribution analysis.

**Usage:**
```bash
copick stats picks [OPTIONS]
```

**Options:**

| Option                  | Type    | Description                                           | Default                      |
|-------------------------|---------|-------------------------------------------------------|------------------------------|
| `-c, --config PATH`     | Path    | Path to the configuration file                        | Uses `COPICK_CONFIG` env var |
| `--runs`                | String  | Specific run names to analyze (multiple allowed)     | All runs                     |
| `--user-id`             | String  | Filter by user ID (multiple allowed)                 | All users                    |
| `--session-id`          | String  | Filter by session ID (multiple allowed)              | All sessions                 |
| `--object-name`         | String  | Filter by pickable object name (multiple allowed)    | All objects                  |
| `--parallel/--no-parallel` | Boolean | Enable parallel processing                           | `no-parallel`               |
| `--workers`             | Integer | Number of workers for parallel processing            | `8`                          |
| `--output`              | Choice  | Output format ('json' or 'table')                    | `table`                      |
| `--debug/--no-debug`    | Boolean | Enable debug logging                                  | `no-debug`                   |

**Examples:**

```bash
# Get statistics for all picks
copick stats picks --config config.json

# Get statistics for specific runs
copick stats picks --config config.json --runs run1 --runs run2

# Get statistics for specific objects and users
copick stats picks --config config.json --object-name ribosome --user-id alice

# Output in JSON format with parallel processing
copick stats picks --config config.json --output json --parallel --workers 12
```

#### :material-vector-triangle: `copick stats meshes`

Generate statistics for meshes including counts and frequency analysis of user/session/object combinations.

**Usage:**
```bash
copick stats meshes [OPTIONS]
```

**Options:**

| Option                  | Type    | Description                                           | Default                      |
|-------------------------|---------|-------------------------------------------------------|------------------------------|
| `-c, --config PATH`     | Path    | Path to the configuration file                        | Uses `COPICK_CONFIG` env var |
| `--runs`                | String  | Specific run names to analyze (multiple allowed)     | All runs                     |
| `--user-id`             | String  | Filter by user ID (multiple allowed)                 | All users                    |
| `--session-id`          | String  | Filter by session ID (multiple allowed)              | All sessions                 |
| `--object-name`         | String  | Filter by pickable object name (multiple allowed)    | All objects                  |
| `--parallel/--no-parallel` | Boolean | Enable parallel processing                           | `no-parallel`               |
| `--workers`             | Integer | Number of workers for parallel processing            | `8`                          |
| `--output`              | Choice  | Output format ('json' or 'table')                    | `table`                      |
| `--debug/--no-debug`    | Boolean | Enable debug logging                                  | `no-debug`                   |

**Examples:**

```bash
# Get statistics for all meshes
copick stats meshes --config config.json

# Get statistics for specific users and sessions
copick stats meshes --config config.json --user-id analyst --session-id session1

# JSON output for integration with other tools
copick stats meshes --config config.json --output json
```

#### :material-layers: `copick stats segmentations`

Generate statistics for segmentations including counts and frequency analysis by various properties.

**Usage:**
```bash
copick stats segmentations [OPTIONS]
```

**Options:**

| Option                      | Type    | Description                                           | Default                      |
|-----------------------------|---------|-------------------------------------------------------|------------------------------|
| `-c, --config PATH`         | Path    | Path to the configuration file                        | Uses `COPICK_CONFIG` env var |
| `--runs`                    | String  | Specific run names to analyze (multiple allowed)     | All runs                     |
| `--user-id`                 | String  | Filter by user ID (multiple allowed)                 | All users                    |
| `--session-id`              | String  | Filter by session ID (multiple allowed)              | All sessions                 |
| `--name`                    | String  | Filter by segmentation name (multiple allowed)       | All segmentations            |
| `--voxel-size`              | Float   | Filter by voxel size (multiple allowed)              | All voxel sizes              |
| `--multilabel/--no-multilabel` | Boolean | Filter by multilabel status                          | All types                    |
| `--parallel/--no-parallel`  | Boolean | Enable parallel processing                            | `no-parallel`               |
| `--workers`                 | Integer | Number of workers for parallel processing            | `8`                          |
| `--output`                  | Choice  | Output format ('json' or 'table')                    | `table`                      |
| `--debug/--no-debug`        | Boolean | Enable debug logging                                  | `no-debug`                   |

**Examples:**

```bash
# Get statistics for all segmentations
copick stats segmentations --config config.json

# Get statistics for specific segmentation types and voxel sizes
copick stats segmentations --config config.json --name membrane --voxel-size 10.0

# Filter by multilabel segmentations only
copick stats segmentations --config config.json --multilabel

# Comprehensive analysis with parallel processing
copick stats segmentations --config config.json --parallel --output json
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

### Synchronize Data Between Projects

Synchronize data between different Copick projects:

```bash
# Basic synchronization of all data types
copick sync picks -c source_config.json --target-config target_config.json --log
copick sync meshes -c source_config.json --target-config target_config.json --log
copick sync segmentations -c source_config.json --target-config target_config.json --log
copick sync tomograms -c source_config.json --target-config target_config.json --log

# Sync from CryoET Data Portal to local project
copick sync picks \
    --source-dataset-ids "12345,67890" \
    --target-config local_project.json \
    --max-workers 8 --log

# Sync with name mapping and user filtering
copick sync picks -c source_config.json --target-config target_config.json \
    --source-runs "run1,run2" --target-runs "run1:experiment_A,run2:experiment_B" \
    --source-objects "ribosome,membrane" --target-objects "ribosome:large_ribosomal_subunit,membrane:plasma_membrane" \
    --source-users "user1,user2" --target-users "user1:analyst1,user2:analyst2" \
    --exist-ok --log

# Selective synchronization of specific voxel spacings and segmentation types
copick sync segmentations -c source_config.json --target-config target_config.json \
    --voxel-spacings "10.0,20.0" \
    --source-names "membrane,organelle" --target-names "membrane:cell_membrane,organelle:mitochondria" \
    --log

copick sync tomograms -c source_config.json --target-config target_config.json \
    --voxel-spacings "10.0" \
    --source-tomo-types "wbp,denoised" --target-tomo-types "wbp:processed,denoised:clean" \
    --log
```

### Create Depositable View for Data Portal

Prepare your copick project for upload to the CryoET Data Portal:

```bash
# Basic deposit with all picks and meshes from a filesystem project
copick deposit -c project.json --target-dir /path/to/deposit \
    --picks "*:*/*" --meshes "*:*/*"

# Deposit specific data types with filters
copick deposit -c project.json --target-dir /path/to/deposit \
    --picks "ribosome:*/*" --picks "proteasome:*/*" \
    --segmentations "membrane:*/*@10.0" \
    --tomograms "wbp@10.0"

# Deposit from data portal project (automatic run naming)
# Runs will be transformed to: {dataset_id}_{portal_run_name}_{portal_run_id}
copick deposit -c portal_config.json --target-dir /path/to/deposit \
    --picks "proteasome:*/*" --meshes "membrane:*/*"

# Deposit specific runs with custom prefix
copick deposit -c project.json --target-dir /path/to/deposit \
    --run-names "TS_001,TS_002,TS_003" \
    --run-name-prefix "experiment_A_" \
    --picks "*:*/*" --max-workers 16

# Use regex to extract run names
# For runs like "Position_60_7_Vol_CTF", extracts "Position_60_7"
copick deposit -c project.json --target-dir /path/to/deposit \
    --run-name-regex "^(Position_.*)_Vol_CTF" \
    --tomograms "wbp@10.0" --tomograms "denoised@10.0"

# Deposit multiple projects to same target directory (successive executions)
copick deposit -c project1.json --target-dir /deposit --run-name-prefix "proj1_" \
    --picks "*:*/*"
copick deposit -c project2.json --target-dir /deposit --run-name-prefix "proj2_" \
    --picks "*:*/*"

# Verify the deposited structure
ls -la /deposit/ExperimentRuns/
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

# Test synchronization with debug logging
copick sync picks -c source_config.json --target-config target_config.json --debug --log

# Test deposit with debug logging
copick deposit -c project.json --target-dir /tmp/test_deposit \
    --picks "*:*/*" --debug
```
