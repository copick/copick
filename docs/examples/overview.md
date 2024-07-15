

## Setup

**copick** projects can be distributed across multiple storage backends. The following short tutorials outline the most
common setups, and provide template configuration files for each case.

<div class="grid cards" markdown>

-   :fontawesome-solid-hard-drive:{ .lg .middle }   __Local Project__

    ---

    All data is accessible on the local filesystem.

    [:octicons-arrow-right-24: Learn more](setup/local.md)

-   :fontawesome-solid-circle-nodes:{ .lg .middle } __cryoET Data Portal Project__

    ---

    Static data is accessed via the [CZ cryoET Data Portal](https://cryoetdataportal.czscience.com/).

    [:octicons-arrow-right-24: Learn more](setup/data_portal.md)

-   :fontawesome-solid-share-nodes:{ .lg .middle }   __Shared Project__

    ---

    Some or all data is stored on a shared filesystem.

    [:octicons-arrow-right-24: Learn more](setup/shared.md)

-   :fontawesome-solid-cloud:{ .lg .middle } __S3 Project__

    ---

    Some or all data is stored on AWS or local S3.

    [:octicons-arrow-right-24: Learn more](setup/aws_s3.md)

-   :fontawesome-solid-terminal:{ .lg .middle } __SSH Project__

    ---

    Some or all data is stored on a filesystem accessible via SSH.

    [:octicons-arrow-right-24: Learn more](setup/ssh.md)

[//]: # (-   :fontawesome-solid-file-zipper:{ .lg .middle } __ZIP Project__)

[//]: # ()
[//]: # (    ---)

[//]: # ()
[//]: # (    Some or all data is stored in a ZIP archive.)

[//]: # (    )
[//]: # (    [:octicons-arrow-right-24: Learn more]&#40;setup/zip.md&#41;)

</div>



## Tutorials

The following tutorials provide step-by-step instructions for using copick to perform specific curation or analysis
tasks.


<div class="grid cards" markdown>

-   :fontawesome-solid-truck-fast:{ .lg .middle }   __Quickstart__

    ---

    Install **copick** and set up a simple project.

    [:octicons-arrow-right-24: Learn more](../quickstart.md)


-   :fontawesome-solid-circle-nodes:{ .lg .middle }   __Data Portal__

    ---

    Accessing data from the CZ cryoET Data Portal and creating new
    annotations for data portal tomograms.

    [:octicons-arrow-right-24: Learn more](tutorials/data_portal.md)

-   :fontawesome-solid-x:{ .lg .middle } __ChimeraX-copick__

    ---

    Using the ChimeraX-copick interface to visualize data from a copick project.

    [:octicons-arrow-right-24: Learn more](tutorials/chimerax.md)

-   :fontawesome-solid-image:{ .lg .middle } __Album__

    ---

    Creating album-based solutions to process copick data.

    [:octicons-arrow-right-24: Learn more](tutorials/album.md)


-   :fontawesome-solid-pallet:{ .lg .middle } __Sample Boundaries__

    ---

    An end-to-end tutorial on how to train a neural network to predict sample boundaries.

    [:octicons-arrow-right-24: Learn more](tutorials/sample_boundaries.md)

-   :fontawesome-solid-circle-notch:{ .lg .middle } __membrain-seg__

    ---

    Running the Membrain-seg segmentation pipeline on a copick project.

    [:octicons-arrow-right-24: Learn more](tutorials/membrain.md)

</div>
