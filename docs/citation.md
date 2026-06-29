# Citation

If you use **copick** in your research, please cite the copick paper. Depending on the tools and data
you access through copick, please also cite the relevant references below.

## copick

> Ermel, U. H., Schwartz, J., Zhao, Z., Ji, D., Peck, A., Yu, Y., Paraan, M., Carragher, B.,
> Frangakis, A. S., & Harrington, K. I. S. (2026). copick: An open dataset interface and toolkit for
> collaborative annotation and analysis of cryo-electron tomography data. *Protein Science*, 35(5).

DOI: [10.1002/pro.70578](https://doi.org/10.1002/pro.70578)

??? quote "BibTeX"
    ```bibtex
    @article{ermel2026copick,
      author  = {Ermel, Utz Heinrich and Schwartz, Jonathan and Zhao, Zhuowen and Ji, Daniel
                 and Peck, Ariana and Yu, Yue and Paraan, Mohammadreza and Carragher, Bridget
                 and Frangakis, Achilleas S. and Harrington, Kyle I. S.},
      title   = {copick: An open dataset interface and toolkit for collaborative annotation
                 and analysis of cryo-electron tomography data},
      journal = {Protein Science},
      volume  = {35},
      number  = {5},
      year    = {2026},
      doi     = {10.1002/pro.70578}
    }
    ```

## ArtiaX

copick's particle and orientation handling — and the [ChimeraX-copick](tools.md#chimerax-copick)
plugin — build on **ArtiaX**. If you use copick to visualize or curate particles in ChimeraX, please
also cite:

> Ermel, U. H., Arghittu, S. M., & Frangakis, A. S. (2022). ArtiaX: An electron tomography toolbox
> for the interactive handling of sub-tomograms in UCSF ChimeraX. *Protein Science*, 31(12).

DOI: [10.1002/pro.4472](https://doi.org/10.1002/pro.4472)

??? quote "BibTeX"
    ```bibtex
    @article{ermel2022artiax,
      author  = {Ermel, Utz H. and Arghittu, Serena M. and Frangakis, Achilleas S.},
      title   = {ArtiaX: An electron tomography toolbox for the interactive handling of
                 sub-tomograms in UCSF ChimeraX},
      journal = {Protein Science},
      volume  = {31},
      number  = {12},
      year    = {2022},
      doi     = {10.1002/pro.4472}
    }
    ```

## Related tools

copick integrates with several external tools and data sources. If your work relies on one of them
through copick, please also cite its reference.

### membrain-seg

A pretrained network for membrane segmentation, run through copick as `copick inference membrain-seg`
(see the [tutorial](examples/tutorials/membrain.md)).

> Lamm, L., Zufferey, S., Zhang, H., Righetto, R. D., Waltz, F., Wietrzynski, W., Yamauchi, K. A.,
> Burt, A., Liu, Y., Martinez-Sanchez, A., Ziegler, S., Isensee, F., Schnabel, J. A., Engel, B. D.,
> & Peng, T. (2024). MemBrain v2: an end-to-end tool for the analysis of membranes in cryo-electron
> tomography. *bioRxiv*.

DOI: [10.1101/2024.01.05.574336](https://doi.org/10.1101/2024.01.05.574336)

### easymode

Pretrained, general-purpose 3D U-Nets for segmenting common cellular features, run through copick as
`copick inference easymode` (see the [tutorial](examples/tutorials/easymode.md)).

> So-Last *et al.* (2026). Easymode: general pretrained networks for cellular cryo-ET enable flexible
> approaches to subtomogram averaging. *bioRxiv*.

DOI: [10.64898/2026.05.19.726344](https://www.biorxiv.org/content/10.64898/2026.05.19.726344v1)

### CZ cryoET Data Portal

copick can read datasets directly from the [CZ cryoET Data Portal](https://cryoetdataportal.czscience.com/)
(see the [tutorial](examples/tutorials/data_portal.md)). Please cite the data portal:

> Ermel, U., Cheng, A., Ni, J. X., Gadling, J., Venkatakrishnan, M., Evans, K., Asuncion, J., Sweet, A.,
> Pourroy, J., Wang, Z. S., Khandwala, K., Nelson, B., McCarthy, D., Wang, E. M., Agarwal, R., &
> Carragher, B. (2024). A data portal for providing standardized annotations for cryo-electron
> tomography. *Nature Methods*, 21(12), 2200–2202.

DOI: [10.1038/s41592-024-02477-2](https://doi.org/10.1038/s41592-024-02477-2)

When you use portal data, also cite the specific dataset(s) you used — each dataset on the portal lists
its own citation and DOI.
