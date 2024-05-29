
The overlay implementation is an extension of the abstract **copick** API implementation that adds methods to seamlessly overlay data from two
different sources. Each overlay implementation is a subclass of the corresponding abstract data entity and implements
methods to overlay data from two sources. The overlay implementations are defined in the `copick.impl.overlay` module.

One source is considered read-only ('static'), while the other source is considered read-write ('overlay').

****

[](){#CopickRunOverlay}
::: copick.impl.overlay.CopickRunOverlay
    options:
        filters:
            - "^."
            - "^_"

****

[](){#CopickObjectOverlay}
::: copick.impl.overlay.CopickObjectOverlay

****

[](){#CopickPicksOverlay}
::: copick.impl.overlay.CopickPicksOverlay

****

[](){#CopickMeshOverlay}
::: copick.impl.overlay.CopickMeshOverlay

****

[](){#CopickSegmentationOverlay}
::: copick.impl.overlay.CopickSegmentationOverlay

****

[](){#CopickVoxelSpacingOverlay}
::: copick.impl.overlay.CopickVoxelSpacingOverlay
    options:
        filters:
            - "^."
            - "^_"

****

[](){#CopickTomogramOverlay}
::: copick.impl.overlay.CopickTomogramOverlay
    options:
        filters:
            - "^."
            - "^_"

****

[](){#CopickFeaturesOverlay}
::: copick.impl.overlay.CopickFeaturesOverlay
