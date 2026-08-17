# Development benchmark baseline: 2026-08-17

This pre-PR baseline exercises the default representative cases with one read
sample per operation. The local and Moto-S3 runs used the same Apple Silicon
host, Python 3.13.3, Zarr 3.3.0, NumPy 2.4.2, `(128, 128, 128)` inner chunks,
and the deterministic benchmark input. Moto listened on loopback, so these
timings validate the code path rather than approximate production S3 latency.

## Local filesystem

| Case | Operation | Elapsed (s) | Data reads | Read bytes | Data writes | Write bytes | Peak RSS increase | I/O / logical bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| small | write full level | 0.276215 | 1 | 0 | 1 | 4468500 | 68075520 | 0.87× |
| small | read full volume | 0.006093 | 1 | 4468500 | 0 | 0 | 49152 | 0.87× |
| small | read one inner chunk | 0.005549 | 1 | 4468500 | 0 | 0 | 32768 | 0.87× |
| small | read multiple inner chunks | 0.006144 | 1 | 4468500 | 0 | 0 | 32768 | 12.99× |
| small | read small region | 0.005973 | 1 | 4468500 | 0 | 0 | 49152 | 2181.88× |
| small | write small region | 0.027302 | 1 | 4468500 | 1 | 4467402 | 32768 | 4363.23× |
| large | write full level | 0.338542 | 1 | 0 | 1 | 58157881 | 120045568 | 0.86× |
| large | read full volume | 0.118849 | 1 | 58157881 | 0 | 0 | 49152 | 0.86× |
| large | read one inner chunk | 0.008998 | 2 | 7161993 | 0 | 0 | 32768 | 0.85× |
| large | read multiple inner chunks | 0.047329 | 5 | 57294330 | 0 | 0 | 49152 | 6.83× |
| large | read small region | 0.008022 | 2 | 7161993 | 0 | 0 | 32768 | 3497.07× |
| large | write small region | 0.059055 | 1 | 58157881 | 1 | 58157772 | 7094272 | 56794.75× |

## Moto S3

| Case | Operation | Elapsed (s) | Data reads | Read bytes | Data writes | Write bytes | Peak RSS increase | I/O / logical bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| small | write full level | 0.499739 | 1 | 0 | 1 | 4468500 | 65617920 | 0.87× |
| small | read full volume | 0.012890 | 1 | 4468500 | 0 | 0 | 212992 | 0.87× |
| small | read one inner chunk | 0.010166 | 1 | 4468500 | 0 | 0 | 32768 | 0.87× |
| small | read multiple inner chunks | 0.010245 | 1 | 4468500 | 0 | 0 | 65536 | 12.99× |
| small | read small region | 0.008784 | 1 | 4468500 | 0 | 0 | 65536 | 2181.88× |
| small | write small region | 0.040401 | 1 | 4468500 | 1 | 4467402 | 49152 | 4363.23× |
| large | write full level | 0.525222 | 1 | 0 | 1 | 58157881 | 234569728 | 0.86× |
| large | read full volume | 0.127339 | 1 | 58157881 | 0 | 0 | 12386304 | 0.86× |
| large | read one inner chunk | 0.019497 | 2 | 7161993 | 0 | 0 | 32768 | 0.85× |
| large | read multiple inner chunks | 0.068266 | 5 | 57294330 | 0 | 0 | 81920 | 6.83× |
| large | read small region | 0.018907 | 2 | 7161993 | 0 | 0 | 32768 | 3497.07× |
| large | write small region | 0.161032 | 1 | 58157881 | 1 | 58157772 | 9125888 | 56794.75× |

Both backends wrote exactly one data object for each full level, retained a
one-element shard grid after the region update, and reproduced every expected
value. The identical payload counts show that the store access plan is stable
across local and S3; elapsed time remains topology-specific.

The amplification baseline is the uncompressed byte size of the requested or
updated array selection. For the `8 × 8 × 8` float32 region, that is 2,048
logical bytes; metadata and transport-protocol overhead are not included.

The benchmark is run locally on demand. Collect local, S3-compatible, and SSH
reports in the same environment when a comparable three-backend result set is
needed. The main test workflow's MLCroissant Zarr v3 corpus job supplies the
remaining correctness coverage.
