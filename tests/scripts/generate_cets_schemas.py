"""Vendor the JSON Schemas of the CETS data models that copick's stored metadata targets.

copick does not depend on ``cets_data_model``; its tests validate the CETS parts of stored metadata against JSON
Schemas generated from the targeted CETS version and kept in ``tests/data/cets/<commit>/``. Run this script with a
Python environment in which that version of ``cets_data_model`` is installed (Python >= 3.11), e.g.::

    git -C cets-data-models archive <commit> | tar -x -C /tmp/cets-src
    uv venv --python 3.12 /tmp/cets-env && uv pip install --python /tmp/cets-env/bin/python /tmp/cets-src
    /tmp/cets-env/bin/python tests/scripts/generate_cets_schemas.py --commit <commit> --base <base commit>

and update ``CETS_TARGET`` in ``copick.util.cets`` to the same commit.
"""

import argparse
import datetime
import json
from importlib import metadata
from pathlib import Path

#: The CETS models whose schemas are vendored.
MODELS = (
    "TiltSeries",
    "TiltImage",
    "AcquisitionSession",
    "Instrument",
    "Alignment",
    "ProjectionAlignment",
    "Tomogram",
    "Region",
    "Dataset",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--commit", required=True, help="cets-data-models commit the installed package was built from")
    parser.add_argument("--base", default=None, help="upstream commit the targeted commit is based on")
    parser.add_argument("--repository", default="TomoBabel/cets-data-models")
    parser.add_argument("--output", type=Path, default=None, help="default: tests/data/cets/<commit>")
    args = parser.parse_args()

    from cets_data_model.models import models

    output = args.output or Path(__file__).resolve().parents[1] / "data" / "cets" / args.commit
    output.mkdir(parents=True, exist_ok=True)
    for name in MODELS:
        schema = getattr(models, name).model_json_schema(mode="validation")
        (output / f"{name}.schema.json").write_text(json.dumps(schema, indent=1, sort_keys=True) + "\n")

    provenance = {
        "repository": args.repository,
        "commit": args.commit,
        "base": args.base,
        "package_version": metadata.version("cets_data_model"),
        "models": list(MODELS),
        "generator": "tests/scripts/generate_cets_schemas.py",
        "generated": datetime.datetime.now(tz=datetime.timezone.utc).date().isoformat(),
    }
    (output / "PROVENANCE.json").write_text(json.dumps(provenance, indent=1) + "\n")
    print(f"Wrote {len(MODELS)} schemas to {output}")


if __name__ == "__main__":
    main()
