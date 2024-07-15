<figure markdown="span">
  ![data-portal-project](../../assets/data_portal_light.png#only-light)
  ![data-portal-project](../../assets/data_portal_dark.png#only-dark)
  <figcaption>copick project setup static data from the CZ cryoET data portal.</figcaption>
</figure>

copick has direct integration with the CZ cryoET Data Portal python API. This allows users to access data from the
portal and create new annotations for data portal tomograms. Datasets to be curated can be selected by dataset ID.

The data portal project is a special project type that is created by setting the `cryoet-data-portal` configuration type.
This project type is can be used with any other overlay-backend. Choose one below for more information on how to set up
your project.

Choose your overlay backend:

=== "Local"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_local_static_data_portal.json"
        ```

    --8<-- "instructions/local_overlay.md"

    --8<-- "instructions/data_portal_static.md"

=== "S3"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_s3_static_data_portal.json"
        ```

    --8<-- "instructions/s3_overlay.md"

    --8<-- "instructions/data_portal_static.md"

=== "SMB Share"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_smb_static_data_portal.json"
        ```

    --8<-- "instructions/shared_overlay.md"

    --8<-- "instructions/data_portal_static.md"

=== "SSH"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_ssh_static_data_portal.json"
        ```

    --8<-- "instructions/ssh_overlay.md"

    --8<-- "instructions/data_portal_static.md"
