"""Fetch and checksum the immutable copick test corpus for CI fan-out."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pooch

sys.path.insert(0, str(Path(__file__).parents[1]))

from corpus_registry import ARCHIVE_NAME, CORPUS_DIGEST, CORPUS_DOI  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True, help="Directory that receives the verified archive")
    args = parser.parse_args()
    corpus = pooch.create(
        path=args.cache,
        base_url=f"doi:{CORPUS_DOI}",
        registry={ARCHIVE_NAME: CORPUS_DIGEST},
    )
    print(corpus.fetch(ARCHIVE_NAME))


if __name__ == "__main__":
    main()
