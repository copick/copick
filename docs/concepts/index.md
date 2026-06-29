# Concepts

Understand how **copick** represents cryoET data, the geometric conventions it follows, and the
processing tools built on top of the data model.

<div class="grid cards" markdown>

-   :fontawesome-solid-layer-group:{ .lg .middle } __Data Model__

    ---

    The object hierarchy — runs, voxel spacings, tomograms, picks, meshes, and segmentations — and
    how it maps onto storage.

    [:octicons-arrow-right-24: Learn more](../datamodel.md)

-   :fontawesome-solid-ruler-combined:{ .lg .middle } __Geometry Conventions__

    ---

    Coordinate systems, array ordering, multiscale pyramids, and the 4×4 transforms copick uses for
    points and orientations.

    [:octicons-arrow-right-24: Learn more](../geometry.md)

-   :fontawesome-solid-wand-magic-sparkles:{ .lg .middle } __Processing Tools__

    ---

    Convert between picks, segmentations, and meshes; process volumes and segmentations; and run
    spatial / boolean operations.

    [:octicons-arrow-right-24: Learn more](../processing_tools.md)

-   :fontawesome-solid-hard-drive:{ .lg .middle } __Storage Backends__

    ---

    Access data on local, shared, S3, SSH, or CZ cryoET Data Portal storage through the same API.

    [:octicons-arrow-right-24: Setup recipes](../get-started/index.md)

</div>
