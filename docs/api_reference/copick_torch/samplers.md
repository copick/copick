# Samplers

Samplers for handling class imbalance when training particle classifiers on cryoET data.

## ClassBalancedSampler

Draws samples so that each class is represented roughly equally per mini-batch, using inverse-frequency
weighting.

::: copick_torch.samplers.ClassBalancedSampler
    options:
        show_root_heading: true
        show_root_full_path: true
