The Embrella implementation is a concrete implementation of the abstract copick API that reads tomograms in place from
an [Embrella](https://github.com/czimaginginstitute/embrella) server's processing tree (no data duplication) and
reads/writes annotations to the per-session copick overlay projects managed by Embrella. Tomogram versions (AreTomo3 or
DenoisET processing runs and reconstruction types) are selected per session in the configuration. The Embrella
implementation is defined in the `copick.impl.embrella` module.

## Metadata Models

[](){#CopickConfigEmbrella}
::: copick.impl.embrella.CopickConfigEmbrella

****

[](){#EmbrellaSessionSpec}
::: copick.impl.embrella.EmbrellaSessionSpec

****

[](){#EmbrellaTomoSelection}
::: copick.impl.embrella.EmbrellaTomoSelection

****

[](){#EmbrellaClusterSpec}
::: copick.impl.embrella.EmbrellaClusterSpec


## Data Entities

[](){#CopickRootEmbrella}
::: copick.impl.embrella.CopickRootEmbrella

****

[](){#CopickObjectEmbrella}
::: copick.impl.embrella.CopickObjectEmbrella

****

[](){#CopickRunEmbrella}
::: copick.impl.embrella.CopickRunEmbrella

****

[](){#CopickPicksEmbrella}
::: copick.impl.embrella.CopickPicksEmbrella

****

[](){#CopickMeshEmbrella}
::: copick.impl.embrella.CopickMeshEmbrella

****

[](){#CopickSegmentationEmbrella}
::: copick.impl.embrella.CopickSegmentationEmbrella

****

[](){#CopickVoxelSpacingEmbrella}
::: copick.impl.embrella.CopickVoxelSpacingEmbrella

****

[](){#CopickTomogramEmbrella}
::: copick.impl.embrella.CopickTomogramEmbrella

****

[](){#CopickFeaturesEmbrella}
::: copick.impl.embrella.CopickFeaturesEmbrella
