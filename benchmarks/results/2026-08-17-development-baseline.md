# Development benchmark baseline: 2026-08-17

This pre-PR baseline exercises the default representative cases with one read
sample per operation. The local and Moto-S3 runs used the same Apple Silicon
host, Python 3.13.3, Zarr 3.3.0, NumPy 2.4.2, `(128, 128, 128)` inner chunks,
and the deterministic benchmark input. Moto listened on loopback, so these
timings validate the code path rather than approximate production S3 latency.

## Local filesystem

| Case | Operation | Elapsed (s) | Data reads | Read bytes | Data writes | Write bytes | Peak RSS | I/O / logical bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| small | write full level | 0.226830 | 1 | 0 | 1 | 4468500 | 140754944 | 0.87× |
| small | read full volume | 0.004914 | 1 | 4468500 | 0 | 0 | 149307392 | 0.87× |
| small | read one inner chunk | 0.004594 | 1 | 4468500 | 0 | 0 | 159678464 | 0.87× |
| small | read multiple inner chunks | 0.004551 | 1 | 4468500 | 0 | 0 | 159694848 | 12.99× |
| small | read small region | 0.004388 | 1 | 4468500 | 0 | 0 | 159727616 | 2181.88× |
| small | write small region | 0.022230 | 1 | 4468500 | 1 | 4467402 | 159727616 | 4363.23× |
| large | write full level | 0.179001 | 1 | 0 | 1 | 58157881 | 525926400 | 0.86× |
| large | read full volume | 0.070272 | 1 | 58157881 | 0 | 0 | 661848064 | 0.86× |
| large | read one inner chunk | 0.005665 | 2 | 7161993 | 0 | 0 | 797720576 | 0.85× |
| large | read multiple inner chunks | 0.023103 | 5 | 57294330 | 0 | 0 | 857604096 | 6.83× |
| large | read small region | 0.005273 | 2 | 7161993 | 0 | 0 | 857604096 | 3497.07× |
| large | write small region | 0.029523 | 1 | 58157881 | 1 | 58157772 | 864665600 | 56794.75× |

## Moto S3

| Case | Operation | Elapsed (s) | Data reads | Read bytes | Data writes | Write bytes | Peak RSS | I/O / logical bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| small | write full level | 0.286433 | 1 | 0 | 1 | 4468500 | 177700864 | 0.87× |
| small | read full volume | 0.008749 | 1 | 4468500 | 0 | 0 | 188760064 | 0.87× |
| small | read one inner chunk | 0.008390 | 1 | 4468500 | 0 | 0 | 199213056 | 0.87× |
| small | read multiple inner chunks | 0.008093 | 1 | 4468500 | 0 | 0 | 199524352 | 12.99× |
| small | read small region | 0.007781 | 1 | 4468500 | 0 | 0 | 199540736 | 2181.88× |
| small | write small region | 0.037194 | 1 | 4468500 | 1 | 4467402 | 199557120 | 4363.23× |
| large | write full level | 0.322217 | 1 | 0 | 1 | 58157881 | 671596544 | 0.86× |
| large | read full volume | 0.089896 | 1 | 58157881 | 0 | 0 | 856162304 | 0.86× |
| large | read one inner chunk | 0.017782 | 2 | 7161993 | 0 | 0 | 991985664 | 0.85× |
| large | read multiple inner chunks | 0.046479 | 5 | 57294330 | 0 | 0 | 1051852800 | 6.83× |
| large | read small region | 0.015776 | 2 | 7161993 | 0 | 0 | 1051852800 | 3497.07× |
| large | write small region | 0.150503 | 1 | 58157881 | 1 | 58157772 | 1059258368 | 56794.75× |

Both backends wrote exactly one data object for each full level, retained a
one-element shard grid after the region update, and reproduced every expected
value. The identical payload counts show that the store access plan is stable
across local and S3; elapsed time remains topology-specific.

The amplification baseline is the uncompressed byte size of the requested or
updated array selection. For the `8 × 8 × 8` float32 region, that is 2,048
logical bytes; metadata and transport-protocol overhead are not included.

The pull-request workflow produces fresh local, Moto-S3, and container-SSH
JSON/Markdown artifacts on a common Ubuntu runner. Those artifacts, rather
than this development-host baseline, are the comparable three-backend result
set. The main test workflow's named MLCroissant Zarr v3 parity job supplies the
remaining correctness evidence.
