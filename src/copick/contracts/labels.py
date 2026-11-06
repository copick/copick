"""What the values of a label volume mean.

Three kinds of "not an object" are kept apart:

- **unknown**: value 0 in an annotation. Nobody said anything about the voxel; it is not background.
- **background**: a class a person painted (``role="background"``), or value 0 of a model output that declares
  ``zero="background"``.
- **inferred**: rows a training policy derived from unknown voxels (for example typical-looking voxels used as
  background). They are recorded as :class:`InferredLabels` next to the annotation and never written into it.

Object classes state what structure they label: a ``membrane`` (the bilayer), a ``compartment`` (the volume it
encloses), a ``particle``, a ``filament`` or ``other``. Whether values are classes or instance IDs is the schema's
``encoding``.
"""

from typing import Dict, List, Literal, Optional, Union

import numpy as np
from pydantic import Field, model_validator

from copick.contracts._common import Contract, Digest

UNKNOWN = 0
"""Label value of an unannotated voxel."""

Structure = Literal["membrane", "compartment", "particle", "filament", "other"]
ClassRole = Literal["background", "object"]


class LabelClass(Contract):
    """One semantic class: the label value it is stored as, and what it means."""

    value: int = Field(ge=1, description="Stored label value; 0 is reserved.")
    name: str = Field(min_length=1)
    role: ClassRole
    structure: Optional[Structure] = Field(default=None, description="Required for objects; absent for background.")
    pickable_object: Optional[str] = Field(default=None, description="Name of the copick pickable object, if any.")
    color: Optional[List[int]] = Field(default=None, min_length=3, max_length=4)

    @model_validator(mode="after")
    def _structure_matches_role(self) -> "LabelClass":
        if self.role == "object" and self.structure is None:
            raise ValueError(f"object class '{self.name}' must state its structure")
        if self.role == "background" and self.structure is not None:
            raise ValueError(f"background class '{self.name}' has no structure")
        return self


class InstanceClass(Contract):
    """The object whose instances an instance-encoded volume numbers 1, 2, ..."""

    name: str = Field(min_length=1)
    structure: Structure
    pickable_object: Optional[str] = None


class LabelSchema(Contract):
    """Meaning of every value of a label volume.

    ``semantic``: each nonzero value is one of ``classes``. ``instance``: each nonzero value is one instance of
    ``instance_class``. ``zero`` says what 0 means: ``unknown`` (always, for annotations) or ``background`` (a model
    output that assigns every voxel). If 0 means background, no class may also have the background role.
    """

    encoding: Literal["semantic", "instance"]
    zero: Literal["unknown", "background"] = "unknown"
    classes: List[LabelClass] = Field(default_factory=list)
    instance_class: Optional[InstanceClass] = None

    @model_validator(mode="after")
    def _consistent(self) -> "LabelSchema":
        if self.encoding == "instance":
            if self.instance_class is None or self.classes:
                raise ValueError("an instance schema has an instance_class and no classes")
            return self
        if self.instance_class is not None or not self.classes:
            raise ValueError("a semantic schema has classes and no instance_class")
        values = [c.value for c in self.classes]
        names = [c.name for c in self.classes]
        if len(set(values)) != len(values) or len(set(names)) != len(names):
            raise ValueError("class values and names must be unique")
        backgrounds = [c.name for c in self.classes if c.role == "background"]
        if len(backgrounds) > 1:
            raise ValueError(f"at most one background class, found {backgrounds}")
        if backgrounds and self.zero == "background":
            raise ValueError("0 already means background; a background class would make it ambiguous")
        return self

    def background_value(self) -> Optional[int]:
        """The stored value of the background class, if the schema has one."""
        return next((c.value for c in self.classes if c.role == "background"), None)

    def role_of(self, value: int) -> str:
        """``unknown``, ``background``, ``object`` or ``instance`` for a stored value; ValueError if undeclared."""
        if value == UNKNOWN:
            return self.zero
        if self.encoding == "instance":
            if value < 0:
                raise ValueError(f"instance IDs are positive, not {value}")
            return "instance"
        for c in self.classes:
            if c.value == value:
                return c.role
        raise ValueError(f"label value {value} is not declared")

    def check_values(self, array: np.ndarray) -> Dict[int, int]:
        """Voxel count of every value in ``array``; ValueError if a value has no declared meaning."""
        values, counts = np.unique(np.asarray(array), return_counts=True)
        for v in values:
            self.role_of(int(v))
        return {int(v): int(n) for v, n in zip(values, counts, strict=True)}


class InferredLabels(Contract):
    """Training rows a policy derived from unknown voxels, recorded separately from the annotation.

    Enough is recorded to reproduce the selection (policy, implementation pin, parameters including any random
    seed) and to check it (count and digest of the selected flat voxel indices). Inferred rows never change the
    annotation and never count as human labels.
    """

    policy: str = Field(min_length=1, description="Qualified name, e.g. cellcanvas_core.data.seeding.SeededDataManager")
    implementation: str = Field(min_length=1, description="Exact pin of the implementation, e.g. a package version.")
    parameters: Dict[str, Union[bool, int, float, str, None]] = Field(default_factory=dict)
    target_value: int = Field(ge=1, description="Class value the rows are trained as; must be a background class.")
    count: int = Field(ge=0)
    indices_digest: Optional[Digest] = Field(default=None, description="copick.contracts.indices_digest of the voxels.")

    def check_target(self, labels: LabelSchema) -> None:
        if labels.encoding != "semantic" or labels.background_value() != self.target_value:
            raise ValueError(
                f"inferred labels of {self.policy} target value {self.target_value}, which is not the background "
                "class of the label schema",
            )
