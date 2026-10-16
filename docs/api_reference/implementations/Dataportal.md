The filesystem implementation is a concrete implementation of the abstract copick API that reads data from the [cryoET
Data Portal](https://cryoetdataportal.czscience.com/) and reads/writes data to/from any storage supported by `fsspec`.
The filesystem implementation is defined in the `copick.impl.cryoet_data_portal` module.

## Tilt series, alignments and CTF

A portal project serves the portal's tilt series and alignments as read-only copick entities, next to any written to
its overlay:

- **Tilt series** have the type `raw` (or `aligned`, for stacks of aligned images); several of one type are told apart
  with `run.get_tilt_series_list("raw", portal_meta_query={"id": ...})`. Images are read from the portal's OME-Zarr on
  S3. The metadata is built from the portal's records: the stage angle of each image (`raw_angle`), its acquisition
  order (from 0), dose and pre-exposure (`Frame`), and its CTF fit (`PerSectionParameters`; the phase shift is
  converted from radians to degrees). The portal records no amplitude contrast; 0.07 is assumed and marked as a
  default (`amplitude_contrast_source`). `metadata.ctf_status` tells whether all, some or none of the images have a
  CTF fit, or whether a fit has a non-positive defocus.
- **Alignments** are named `{method}-{type}-{portal id}`, e.g. `projectionMatching-local-18924`. Their per-section
  parameters are converted from the portal's convention (pixel shifts, centres at `N/2`) to copick's (see
  [Geometry](../../geometry.md#7-tilt-series-and-alignments)); the reference volume is the portal's alignment volume.
  Of a local alignment only the rigid part is available. The status of an alignment:
    - `author`: per-section parameters that fit the tilt series;
    - `portal_default`: no per-section parameters, all fields at the portal's defaults. The portal creates such a
      placeholder when a deposition holds no alignment;
    - `no_per_section`: no per-section parameters, but not a placeholder;
    - `inconsistent`: parameters that do not fit the tilt series.

    `tilt_series.valid_alignments` lists only `author` alignments, the portal's standard ones first.
- **Tomograms** report the alignment the portal links them to (`tomogram.alignment`, `tomogram.tilt_series`). Linking
  a portal tomogram to an alignment of the overlay (`tomogram.set_alignment(...)`) takes precedence; removing that link
  restores the portal's.

These records are queried once for all configured datasets, on first access to a run's tilt series or alignments (not
when the project is opened), and kept in the portal disk cache next to the annotation data
(`.copick_cache/portal_acq_*.json`; see `copick cache info` and `copick cache clear`).

## Metadata Models

[](){#CopickConfigCDP}
::: copick.impl.cryoet_data_portal.CopickConfigCDP


## Data Entities

[](){#CopickRootCDP}
::: copick.impl.cryoet_data_portal.CopickRootCDP

****

[](){#CopickObjectCDP}
::: copick.impl.cryoet_data_portal.CopickObjectCDP

****

[](){#CopickRunCDP}
::: copick.impl.cryoet_data_portal.CopickRunCDP

****

[](){#CopickPicksCDP}
::: copick.impl.cryoet_data_portal.CopickPicksCDP

****

[](){#CopickMeshCDP}
::: copick.impl.cryoet_data_portal.CopickMeshCDP

****

[](){#CopickSegmentationCDP}
::: copick.impl.cryoet_data_portal.CopickSegmentationCDP

****

[](){#CopickVoxelSpacingCDP}
::: copick.impl.cryoet_data_portal.CopickVoxelSpacingCDP

****

[](){#CopickTiltSeriesCDP}
::: copick.impl.cryoet_data_portal.CopickTiltSeriesCDP

****

[](){#CopickAlignmentCDP}
::: copick.impl.cryoet_data_portal.CopickAlignmentCDP

****

[](){#CopickTomogramCDP}
::: copick.impl.cryoet_data_portal.CopickTomogramCDP

****

[](){#CopickFeaturesCDP}
::: copick.impl.cryoet_data_portal.CopickFeaturesCDP
