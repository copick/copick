# Augmentations

MONAI-compatible 3D augmentations for cryoET subvolumes. They can be composed into a transform
pipeline or applied directly to batches/volumes.

## MixupTransform

Creates virtual training examples by blending pairs of samples (and their labels).

::: copick_torch.augmentations.MixupTransform
    options:
        show_root_heading: true
        show_root_full_path: true

## FourierAugment3D

Frequency-domain augmentation: random frequency dropout, phase noise, and intensity scaling.

::: copick_torch.augmentations.FourierAugment3D
    options:
        show_root_heading: true
        show_root_full_path: true
