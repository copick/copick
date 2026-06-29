# Filters & Fitting

Frequency-domain filters and downsampling for 3D volumes, geometric slab fitting from picks or
segmentations, and a helper for multi-GPU parallel processing.

## Filters

### Filter3D

A 3D cosine band-pass / low-pass / high-pass filter.

::: copick_torch.filters.bandpass.Filter3D
    options:
        show_root_heading: true
        show_root_full_path: true

### FourierRescale3D

Downsamples 3D volumes via Fourier cropping.

::: copick_torch.filters.downsample.FourierRescale3D
    options:
        show_root_heading: true
        show_root_full_path: true

## Fitting

Fit 3D slabs (parallel planes / spline surfaces) to membrane-like structures.

### slab_from_picks

::: copick_torch.fitting.slab_from_picks.slab_from_picks
    options:
        show_root_heading: true
        show_root_full_path: true

### slab_from_segmentation

::: copick_torch.fitting.slab_from_segmentation.slab_from_segmentation
    options:
        show_root_heading: true
        show_root_full_path: true

## Parallelization

### GPUPool

A thread-safe pool for parallel processing across multiple GPUs.

::: copick_torch.parallelization.GPUPool
    options:
        show_root_heading: true
        show_root_full_path: true
