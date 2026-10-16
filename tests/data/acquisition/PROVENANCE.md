# Test data for tilt-series format import and export

- `10445_TS_105_5.aln`: the AreTomo3 alignment of CryoET Data Portal run TS_105_5 (dataset 10445), from which the
  portal's alignment 18924 was ingested
  (`https://files.cryoetdataportal.cziscience.com/10445/TS_105_5/Alignments/100/`). Copied from the test data of
  TomoBabel/cets-cryoet-data-portal (`tests/data/10445_TS_105_5.aln`, commit deef844). The same run's portal records are
  in `../portal/10445_TS_105_5.json`; the `_CTF.txt` and `_TLT.txt` files the tests use are generated from them.
