# Datasets

`copick-torch` provides PyTorch `Dataset` classes that extract 3D subvolumes around copick picks,
with optional background sampling, caching, and on-the-fly augmentation. Each dataset yields
`(volume, label)` tuples ready for a `DataLoader`.

## MinimalCopickDataset

The simplest dataset — no caching or augmentation, minimal dependencies.

::: copick_torch.minimal_dataset.MinimalCopickDataset
    options:
        show_root_heading: true
        show_root_full_path: true

## SimpleCopickDataset

Adds disk caching (pickle or parquet), augmentation, and class-balancing helpers.

::: copick_torch.dataset.SimpleCopickDataset
    options:
        show_root_heading: true
        show_root_full_path: true

## SplicedMixupDataset

Combines experimental and synthetic tomograms with Gaussian-blended splicing and mixup.

::: copick_torch.dataset.SplicedMixupDataset
    options:
        show_root_heading: true
        show_root_full_path: true

## CopickDataset

The original, full-featured dataset implementation.

::: copick_torch.copick.CopickDataset
    options:
        show_root_heading: true
        show_root_full_path: true
