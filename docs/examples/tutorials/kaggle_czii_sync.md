# Syncing CZII Kaggle Challenge Dataset with Copick

This tutorial demonstrates how to use Copick's sync functionality to reproduce the CZII CryoET Object Identification Kaggle competition dataset structure and naming conventions.

## Competition Overview

The [CZII CryoET Object Identification Competition](https://cryoetdataportal.czscience.com/competition) challenged participants to develop machine learning algorithms that can automatically annotate particles in 3D cellular tomograms. The competition features a phantom dataset containing 6 protein complexes:

1. **Apo-ferritin** - Iron storage protein complex
2. **Beta-amylase** - Starch-degrading enzyme
3. **Beta-galactosidase** - Lactose-metabolizing enzyme
4. **Thyroglobulin** - Thyroid hormone precursor protein
5. **80S ribosome** - Protein synthesis machinery
6. **Virus-like Particles (VLPs)** - Synthetic viral capsids

## Prerequisites

Before starting, ensure you have the required packages installed:

```bash
uv pip install "copick[all]>=1.10.0" "cryoet-data-portal"
```

You'll also need sufficient disk space for the dataset (several GB) and a stable internet connection for downloading from the CryoET Data Portal.

## How To Sync

This example demonstrates how to sync the CZII competition dataset with compatible naming conventions:

```python
import copick
from copick.ops.sync import sync_tomograms, sync_picks
import cryoet_data_portal as cdp

# Step 1: Establish connection and name mappings
# =============================================

# Connect to the CryoET Data Portal
client = cdp.Client()

# Retrieve all runs from dataset 10440 (CZII competition dataset)
runs = cdp.Run.find(client, [cdp.Run.dataset_id == 10440])

# Create mapping from portal run IDs to Kaggle-compatible run names
# Copick normally uses run IDs by default because they are unique,
# while run names may not be unique across multiple cryoET data portal datasets.
portal_runs_to_kaggle_runs = {str(r.id): r.name for r in runs}

# Map portal object names to competition object names
# The portal uses scientific names (Gene Ontology Term/UniProtKB accession),
# while the Kaggle competition uses simplified names
portal_objects_to_kaggle_objects = {
    "beta-galactosidase": "beta-galactosidase",
    "cytosolic-ribosome": "ribosome",
    "virus-like-capsid": "virus-like-particle",
    "ferritin-complex": "apo-ferritin",
    "beta-amylase": "beta-amylase",
    "thyroglobulin": "thyroglobulin",
}

# Step 2: Configure source data access
# ====================================

# Create Copick root pointing to CryoET Data Portal dataset
# The '/tmp/overlay' path won't store anything - it's just required by the API
portal_root = copick.from_czcdp_datasets([10440], '/tmp/overlay')

# Extract and rename pickable objects for the target dataset
objects = []
for obj in portal_root.config.pickable_objects:
    if obj.name in portal_objects_to_kaggle_objects:
        # Create a copy with the Kaggle-compatible name
        kaggle_obj = obj.copy()
        kaggle_obj.name = portal_objects_to_kaggle_objects[obj.name]
        objects.append(kaggle_obj)

# Step 3: Create target dataset structure
# =======================================

# Create new Copick project with Kaggle-compatible structure
# This will store the synchronized data locally.
# Update the paths as needed for your environment.
target_root = copick.new_config(
    '/tmp/czcdp_dataset_demo/copick_config.json',  # Configuration file path
    '/tmp/czcdp_dataset_demo/',      # Data storage directory
    pickable_objects=objects         # Object definitions with correct names
)

# Step 4: Sync tomographic data
# =============================

# Copick constructs the tomogram type from data portal metadata. The competition used
# simplified names for tomograms, so we map the portal's processed tomogram type as well.
sync_tomograms(
    portal_root,                                           # Source: CryoET Data Portal
    target_root,                                           # Target: Local Copick project
    source_runs=list(portal_runs_to_kaggle_runs.keys()),   # All available runs
    target_runs=portal_runs_to_kaggle_runs,                # Run name mapping
    voxel_spacings=[10.012],                               # Competition voxel size
    source_tomo_types=["wbp-denoised-denoiset-ctfdeconv"], # Tomogram type to sync
    target_tomo_types={"wbp-denoised-denoiset-ctfdeconv": "denoised"}, # Mapping to simplified name
    log=True,                                              # Show progress
    exist_ok=True,                                         # Allow overwriting
)

# Step 5: Sync annotation data
# ============================

sync_picks(
    portal_root,                                           # Source: CryoET Data Portal
    target_root,                                           # Target: Local Copick project
    source_runs=list(portal_runs_to_kaggle_runs.keys()),   # All available runs
    target_runs=portal_runs_to_kaggle_runs,                # Run name mapping
    source_objects=list(portal_objects_to_kaggle_objects.keys()), # Portal object names
    target_objects=portal_objects_to_kaggle_objects,       # Kaggle object name mapping
    log=True,                                              # Show progress
    exist_ok=True,                                         # Allow overwriting
)
```

## Expected Outcomes

After running this script, you'll have:

### Local Dataset Structure
```
/tmp/czcdp_dataset_demo/
├── ExperimentRuns/
│   ├── TS_5_4/
│   │   ├── VoxelSpacing10.012/
│   │   │   └── Tomograms/
│   │   │       └── denoised.zarr/
│   │   └── Picks/
│   │       ├── data-portal_74183_apo-ferritin.json
│   │       ├── data-portal_74184_beta-amylase.json
│   │       ├── data-portal_74185_beta-galactosidase.json
│   │       ├── data-portal_74186_ribosome.json
│   │       ├── data-portal_74187_thyroglobulin.json
│   │       └── data-portal_74188_virus-like-particle.json
│   ├── [run_name_2]/
│   └── [additional_runs]/
└── copick_config.json
```


## Next Steps for ML Pipeline Integration

After syncing the data, you can:

1. **Load into ML frameworks**:
```python
import copick
root = copick.from_file('/tmp/czcdp_dataset_demo/copick_config.json')
```

2. **Explore the data**:
```python
# List available runs and objects
for run in root.runs:
    print(f"Run: {run.name}")
    for pick in run.picks:
        print(f"  - {pick.object_name}: {len(pick.points)} particles")
        picks_array, _ = pick.points.numpy()  # Get points as NumPy array
```
