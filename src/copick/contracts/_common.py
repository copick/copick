"""Shared types of the integration contracts."""

import hashlib
from typing import Annotated, List, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "1"
"""Version of every contract document. A change that an existing reader would misinterpret gets a new version."""

ContractVersion = Literal["1"]
"""Literal type of the ``contract_version`` field; keep equal to CONTRACT_VERSION."""

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$", description="'sha256:' and 64 hex digits.")]
Vec3 = Annotated[List[float], Field(min_length=3, max_length=3, description="(z, y, x)")]
Shape3 = Annotated[List[Annotated[int, Field(ge=1)]], Field(min_length=3, max_length=3, description="(z, y, x)")]


class Contract(BaseModel):
    """A contract document: unknown fields are refused, so a misspelled key cannot silently drop meaning."""

    model_config = ConfigDict(extra="forbid")


def label_digest(array: np.ndarray) -> str:
    """Digest of a label volume: its dtype, shape and C-order bytes.

    Two volumes have the same digest only if every voxel, the dtype and the shape are equal, so a digest identifies
    the exact labels an annotation revision or result refers to.
    """
    array = np.ascontiguousarray(array)
    header = f"{array.dtype.str}:{','.join(map(str, array.shape))}:".encode()
    return "sha256:" + hashlib.sha256(header + array.tobytes()).hexdigest()


def indices_digest(indices: np.ndarray) -> str:
    """Digest of a set of flat voxel indices (order-independent), e.g. the voxels a labelling policy inferred."""
    values = np.unique(np.asarray(indices, dtype=np.int64))
    return "sha256:" + hashlib.sha256(values.astype("<i8").tobytes()).hexdigest()
