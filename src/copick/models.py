import json
from typing import Dict, ForwardRef, List, Literal, Optional, Tuple, Union

import numpy as np
from pydantic import BaseModel, Field, validator

PickableObject = ForwardRef("PickableObject")
CopickConfig = ForwardRef("CopickConfig")
CopickLocation = ForwardRef("CopickLocation")
CopickPoint = ForwardRef("CopickPoint")
CopickPicks = ForwardRef("CopickPicks")
CopickTomogram = ForwardRef("CopickTomogram")
CopickVoxelSpacing = ForwardRef("CopickVoxelSpacing")
CopickRun = ForwardRef("CopickRun")
CopickRoot = ForwardRef("CopickRoot")


class PickableObject(BaseModel):
    name: str
    emdb_id: Optional[str] = None
    pdb_id: Optional[str] = None


PickableObject.update_forward_refs()


class CopickConfig(BaseModel):
    name: Optional[str] = "CoPick"
    """Name of the CoPick project."""
    description: Optional[str] = "Let's CoPick!"
    """Description of the CoPick project."""
    version: Optional[str] = "1.0.0"
    """Version of the CoPick API."""

    # Dict[object_name: PickableObject]
    pickable_objects: List[PickableObject]
    """Index for available pickable objects."""

    voxel_spacings: Optional[List[float]] = None
    """Index for available voxel spacings."""

    runs: Optional[List[str]] = None
    """Index for run names."""

    # Dict[voxel_spacing: List of tomogram types]
    tomograms: Optional[Dict[float, List[str]]] = None
    """Index for available voxel spacings and tomogram types."""

    # Dict[object_name: List[pre-pick tool names]]
    available_pre_picks: Optional[Dict[str, List[str]]]
    """Index for available pre-pick tools."""

    @classmethod
    def from_file(cls, filename: str) -> CopickConfig:
        with open(filename) as f:
            return cls(**json.load(f))


class CopickLocation(BaseModel):
    x: float
    y: float
    z: float


class CopickPoint(BaseModel):
    location: CopickLocation
    orientation: Optional[np.ndarray] = np.array(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
    )
    instance_id: Optional[int] = 0
    score: Optional[float] = 1.0

    class Config:
        arbitrary_types_allowed = True

    @validator("orientation")
    def validate_orientation(self, v):
        """Validate the orientation matrix."""
        assert v.shape == (4, 4), "Orientation must be a 4x4 matrix."
        assert v[3, 3] == 1.0, "Last element of orientation matrix must be 1.0."
        assert np.allclose(v[3, :], [0.0, 0.0, 0.0, 1.0]), "Last row of orientation matrix must be [0, 0, 0, 1]."
        return v


class CopickRoot(BaseModel):
    config: Optional[CopickConfig] = None
    """Reference to the configuration for this root. This will only be populated at runtime."""
    runs_: Optional[List[CopickRun]] = None
    """References to the runs for this project. Either populated from config or lazily loaded when CopickRoot.runs is
    accessed."""

    @classmethod
    def from_config(cls, config: CopickConfig) -> CopickRoot:
        clazz = cls(config=config)
        runs = [CopickRun.from_config(config, run_name, clazz) for run_name in config.runs]
        clazz.runs_ = runs
        return clazz

    def query(self) -> List[CopickRun]:
        """Override this method to query for runs."""
        pass

    @property
    def runs(self) -> List[CopickRun]:
        """Retrieve runs via a RESTful interface or filesystem"""
        if self.runs_ is None:
            self.runs_ = self.query()

        return self.runs_

    def materialize(self):
        """Materialize the self-referential tree structure."""
        for run in self.runs:
            run.root = self
            for vs in run.voxel_spacings:
                vs.run = run
                for tom in vs.tomograms:
                    tom.voxel_spacing = vs
            for pick in run.picks:
                pick.run = run

    def refresh(self):
        """Refresh the self-referential tree structure."""
        self.runs_ = self.query()

    #######################
    # Tree Item interface #
    #######################
    def child(self, row) -> CopickRun:
        return self.runs[row]

    def childCount(self) -> int:
        return len(self.runs)

    def childIndex(self) -> Union[int, None]:
        return None

    def data(self, column: int) -> str:
        if column == 0:
            return self.config.name
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2


class CopickRun(BaseModel):
    name: str
    """Name of the run."""
    root: Optional[CopickRoot] = Field(None, exclude=True)
    """Reference to the root this run belongs to. This will only be populated at runtime and is excluded from
    serialization."""
    voxel_spacings_: Optional[List[CopickVoxelSpacing]] = None
    """References to the voxel spacings for this run. Either populated from config or lazily loaded when
    CopickRun.voxel_spacings is accessed."""
    picks_: Optional[List[CopickPicks]] = None
    """References to the picks for this run. Either populated from config or lazily loaded when CopickRun.picks is
    accessed."""

    @classmethod
    def from_config(
        cls,
        config: CopickConfig,
        run_name: str,
        root: CopickRoot,
        user_session_ids: Optional[List[Tuple[str, str]]] = None,
    ) -> CopickRun:
        root.update_forward_refs()
        clazz = cls(name=run_name, root=root)
        voxel_spacings = [CopickVoxelSpacing.from_config(config, run=clazz, voxel_size=vs) for vs in config.tomograms]
        clazz.voxel_spacings_ = voxel_spacings

        picks = []

        # Select all available pre-picks for this run
        avail = config.available_pre_picks.keys()
        avail = [a for a in avail if a[0] == run_name]

        # Pre-defined picks
        for av in avail:
            object_name = av[1]
            prepicks = config.available_pre_picks[av]

            for pp in prepicks:
                cop = CopickPicks(
                    pickable_object_name=object_name,
                    run_name=run_name,
                    user_id=pp,
                    session_id="0",
                )
                picks.append(cop)

        # User picks
        if user_session_ids is not None:
            for user_id, session_id in user_session_ids:
                for po in config.pickable_objects:
                    cop = CopickPicks(
                        pickable_object_name=po,
                        run_name=run_name,
                        user_id=user_id,
                        session_id=session_id,
                    )
                    picks.append(cop)

        clazz.picks_ = picks
        return clazz

    def query_voxelspacings(self) -> List[CopickVoxelSpacing]:
        """Override this method to query for voxel_spacings."""
        pass

    def query_picks(self) -> List[CopickPicks]:
        """Override this method to query for picks."""
        pass

    @property
    def voxel_spacings(self) -> List[CopickVoxelSpacing]:
        """Future location for retrieving voxel spacings via a RESTful interface or filesystem."""
        if self.voxel_spacings_ is None:
            self.voxel_spacings_ = self.query_voxelspacings()

        return self.voxel_spacings_

    @property
    def picks(self) -> List[CopickPicks]:
        """Future location for retrieving picks via a RESTful interface or filesystem."""
        if self.picks_ is None:
            self.picks_ = self.query_picks()

        return self.picks_

    def refresh_picks(self) -> None:
        """Refresh the picks."""
        self.picks_ = self.query_picks()

    def refresh_voxel_spacings(self) -> None:
        """Refresh the voxel spacings."""
        self.voxel_spacings_ = self.query_voxelspacings()

    def refresh(self) -> None:
        """Refresh the children."""
        self.refresh_picks()
        self.refresh_voxel_spacings()

    #######################
    # Tree Item interface #
    #######################
    def child(self, row) -> CopickVoxelSpacing:
        return self.voxel_spacings[row]

    def childCount(self) -> int:
        return len(self.voxel_spacings)

    def childIndex(self) -> Union[int, None]:
        return self.root.runs.index(self)

    def data(self, column: int) -> str:
        if column == 0:
            return self.name
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2


class CopickVoxelSpacing(BaseModel):
    voxel_size: float
    """Voxel spacing for the tomograms."""
    run: Optional[CopickRun] = Field(None, exclude=True)
    """Reference to the run this voxel spacing belongs to. This will only be populated at runtime and is excluded from
    serialization."""
    tomograms_: Optional[List[CopickTomogram]] = None
    """References to the tomograms for this voxel spacing."""

    @classmethod
    def from_config(cls, config: CopickConfig, run: CopickRun, voxel_size: float) -> CopickVoxelSpacing:
        clazz = cls(voxel_size=voxel_size, run=run, _tomograms=[])
        toms = [
            CopickTomogram.from_config(config, voxel_spacing=clazz, tomotype=tt) for tt in config.tomograms[voxel_size]
        ]
        clazz.tomograms_ = toms
        return clazz

    def query(self) -> List[CopickTomogram]:
        """Override this method to query for tomograms."""
        pass

    @property
    def tomograms(self) -> List[CopickTomogram]:
        """Future location for retrieving tomograms via a RESTful interface or filesystem."""
        if self.tomograms_ is None:
            self.tomograms_ = self.query()

        return self.tomograms_

    def refresh(self) -> None:
        """Refresh the children."""
        self.tomograms_ = self.query()

    #######################
    # Tree Item interface #
    #######################
    def child(self, row) -> CopickTomogram:
        return self.tomograms[row]

    def childCount(self) -> int:
        return len(self.tomograms)

    def childIndex(self) -> Union[int, None]:
        return self.run.voxel_spacings.index(self)

    def data(self, column: int) -> str:
        if column == 0:
            return f"VoxelSpacing{self.voxel_size:.3f}"
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2


class CopickTomogram(BaseModel):
    tomotype: str
    """Type of the tomogram."""
    voxel_spacing: Optional[CopickVoxelSpacing] = Field(None, exclude=True)
    """Reference to the voxel spacing this tomogram belongs to. This will only be populated at runtime."""

    @classmethod
    def from_config(
        cls,
        config: CopickConfig,
        voxel_spacing: CopickVoxelSpacing,
        tomotype: str,
    ) -> CopickTomogram:
        return cls(tomotype=tomotype, voxel_spacing=voxel_spacing)

    #######################
    # Tree Item interface #
    #######################
    def child(self, row) -> None:
        return None

    def childCount(self) -> int:
        return 0

    def childIndex(self) -> Union[int, None]:
        return self.run.voxel_spacings.index(self)

    def data(self, column: int) -> str:
        if column == 0:
            return self.tomotype
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2


class CopickPicks(BaseModel):
    pickable_object_name: str
    """Pickable object name from CopickConfig.pickable_objects[X].name"""

    run: Optional[CopickRun] = Field(None, exclude=True)
    """Reference to the run this pick belongs to. This will only be populated at runtime."""

    user_id: str
    """Unique identifier for the user or tool name."""

    session_id: Union[str, Literal["0"]]
    """Unique identifier for the pick session (prevent race if they run multiple instances of napari, ChimeraX, etc)
       If it is 0, this pick was generated by a tool."""

    run_name: str
    """Name of the run this pick belongs to."""
    voxel_spacing: Optional[float]
    """Voxel spacing for the tomogram this pick belongs to."""
    unit: Optional[str] = "angstrom"
    """Unit for the location of the pick."""

    points_: Optional[List[CopickPoint]] = None
    """References to the points for this pick."""

    def load(self) -> List[CopickPoint]:
        """Override this method to load points from a RESTful interface or filesystem."""
        pass

    def store(self):
        """Override this method to store points with a RESTful interface or filesystem."""
        pass

    @property
    def points(self) -> List[CopickPoint]:
        self.points_ = self.load()

        return self.points_


CopickRoot.update_forward_refs(CopickRun=CopickRun)
CopickRun.update_forward_refs(CopickVoxelSpacing=CopickVoxelSpacing, CopickPicks=CopickPicks)
CopickVoxelSpacing.update_forward_refs(CopickTomogram=CopickTomogram)


if __name__ == "__main__":
    conf = CopickConfig.from_file("/Users/utz.ermel/Documents/copick/sample_project/copick_config.json")
    root = CopickRoot.from_config(conf)

    rd = root.dict()
    cr = CopickRoot(**rd)
    cr.materialize()
