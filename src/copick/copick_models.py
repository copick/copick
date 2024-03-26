from typing import Dict, List, Literal, Optional, Tuple, Union

import numpy as np
from pydantic import BaseModel


class PickableObject(BaseModel):
    name: str
    emdb_id: Optional[str] = None
    pdb_id: Optional[str] = None


class CopickConfig(BaseModel):
    name: Optional[str] = "CoPick"
    description: Optional[str] = "Let's CoPick!"
    version: Optional[str] = 1.0

    pickable_objects: Dict[str, PickableObject]

    runs: List[str]
    tomograms: Dict[float, List[str]]  # voxel_spacing: List of tomogram types

    available_pre_picks: Dict[Tuple[str, str], List[str]]  # (run_name, object_name): List of pre-pick tool names


class CopickLocation(BaseModel):
    x: float
    y: float
    z: float
    unit: Optional[str] = "angstrom"


class CopickPoint(BaseModel):
    location: CopickLocation
    orientation: Optional[np.ndarray] = np.array(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
    )
    instance_id: Optional[int] = 0
    score: Optional[float] = 1.0


##########################
# QCoPickModel item data #
##########################
class CopickPicks(BaseModel):
    pickable_object_name: str  # Name from CopickConfig.pickable_objects.keys()

    pick_type = Union[Literal["user"], Literal["tool"]]

    # If user generated picks:
    # Unique identifier for the user
    user_id: Optional[str] = None
    # Unique identifier for the pick session (prevent race if they run multiple instances of napari, ChimeraX, etc)
    session_id: Optional[str] = None

    # If tool generated picks:
    # Name of the tool that generated the picks
    tool_name: Optional[str] = None

    run_name: str
    voxel_spacing: Optional[float]

    _points: Optional[List[CopickPoint]] = None

    def load(self) -> List[CopickPoint]:
        """Override this method to load points from a RESTful interface or filesystem."""
        pass

    def store(self):
        """Override this method to store points with a RESTful interface or filesystem."""
        pass

    @property
    def points(self) -> List[CopickPoint]:
        self._points = self.load()

        return self._points


class CopickTomogram(BaseModel):
    tomotype: str
    voxel_spacing: "CopickVoxelSpacing"
    # _picks: Optional[List[CopickPicks]] = None

    @classmethod
    def from_config(
        cls,
        config: CopickConfig,
        voxel_spacing: "CopickVoxelSpacing",
        tomotype: str,
    ) -> "CopickTomogram":
        return cls(tomotype=tomotype, voxel_spacing=voxel_spacing)

    #####################
    # Qt Item interface #
    #####################
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


class CopickVoxelSpacing(BaseModel):
    voxel_size: float
    run: "CopickRun"
    _tomograms: Optional[List[CopickTomogram]] = None

    @classmethod
    def from_config(cls, config: CopickConfig, run: "CopickRun", voxel_size: float) -> "CopickVoxelSpacing":
        clazz = cls(voxel_spacing=voxel_size, run=run)
        toms = [
            CopickTomogram.from_config(config, voxel_spacing=clazz, tomotype=tt) for tt in config.tomograms[voxel_size]
        ]
        clazz._tomograms = toms
        return clazz

    def query(self) -> List[CopickTomogram]:
        """Override this method to query for tomograms."""
        pass

    @property
    def tomograms(self) -> List[CopickTomogram]:
        """Future location for retrieving tomograms via a RESTful interface or filesystem."""
        if self._tomograms is None:
            self._tomograms = self.query()

        return self._tomograms

    #####################
    # Qt Item interface #
    #####################
    def child(self, row) -> CopickTomogram:
        return self.tomograms[row]

    def childCount(self) -> int:
        return len(self.tomograms)

    def childIndex(self) -> Union[int, None]:
        return self.run.voxel_spacings.index(self)

    def data(self, column: int) -> str:
        if column == 0:
            return f"VoxelSpacing{self.voxel_spacing:.3f}"
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2


class CopickRun(BaseModel):
    name: str
    root: "CopickRoot"
    _voxel_spacings: Optional[List[CopickVoxelSpacing]] = None
    _picks: Optional[List[CopickPicks]] = None

    @classmethod
    def from_config(
        cls,
        config: CopickConfig,
        run_name: str,
        root: "CopickRoot",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> "CopickRun":
        clazz = cls(name=run_name, root=root)
        voxel_spacings = [CopickVoxelSpacing.from_config(config, run=clazz, voxel_size=vs) for vs in config.tomograms]
        clazz._voxel_spacings = voxel_spacings

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
                    tool_name=pp,
                )
                picks.append(cop)

        # User picks
        if user_id is not None:
            for po in config.pickable_objects:
                cop = CopickPicks(
                    pickable_object_name=po,
                    run_name=run_name,
                    user_id=user_id,
                    session_id=session_id,
                )
                picks.append(cop)

        clazz._picks = picks
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
        if self._voxel_spacings is None:
            self._voxel_spacings = self.query_vs()

        return self._voxel_spacings

    @property
    def picks(self) -> List[CopickPicks]:
        """Future location for retrieving picks via a RESTful interface or filesystem."""
        if self._picks is None:
            self._picks = self.query_picks()

        return self._picks

    #####################
    # Qt Item interface #
    #####################
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


class CopickRoot(BaseModel):
    config: Optional[CopickConfig] = None
    _runs: Optional[List[CopickRun]] = None

    @classmethod
    def from_config(cls, config: CopickConfig) -> "CopickRoot":
        clazz = cls(config=config)
        runs = [CopickRun.from_config(config, run_name, clazz) for run_name in config.runs]
        clazz._runs = runs
        return clazz

    def query(self) -> List[CopickRun]:
        """Override this method to query for runs."""
        pass

    @property
    def runs(self) -> List[CopickRun]:
        """Retrieve runs via a RESTful interface or filesystem"""
        if self._runs is None:
            self._runs = self.query()

        return self._runs

    #####################
    # Qt Item interface #
    #####################
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
