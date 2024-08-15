from typing import Any, Dict, Optional, Tuple

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map = {
        Dict[str, Any]: JSON,
    }
    pass


class PickableObject(Base):
    __tablename__ = "pickable_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    label: Mapped[int] = mapped_column(unique=True)
    is_particle: Mapped[bool]

    color_red: Mapped[int] = mapped_column(Integer, nullable=True, default=100)
    color_green: Mapped[int] = mapped_column(Integer, nullable=True, default=100)
    color_blue: Mapped[int] = mapped_column(Integer, nullable=True, default=100)
    color_alpha: Mapped[int] = mapped_column(Integer, nullable=True, default=255)
    emdb_id: Mapped[str] = mapped_column(String, nullable=True)
    pdb_id: Mapped[str] = mapped_column(String, nullable=True)
    go_id: Mapped[str] = mapped_column(String, nullable=True)
    map_threshold: Mapped[float] = mapped_column(Integer, nullable=True)
    radius: Mapped[float] = mapped_column(Integer, nullable=True)

    @property
    def color(self) -> Tuple[int]:
        return (self.color_red, self.color_green, self.color_blue, self.color_alpha)


class CopickPoint(Base):
    __tablename__ = "copick_points"

    # Self
    id: Mapped[int] = mapped_column(primary_key=True)
    location_x: Mapped[float] = mapped_column(Float)
    location_y: Mapped[float] = mapped_column(Float)
    location_z: Mapped[float] = mapped_column(Float)
    transform: Mapped[Dict[str, Any]]
    instance_id: Mapped[Optional[int]]
    score: Mapped[Optional[float]]

    # Parent Relationships
    pick_id: Mapped[int] = mapped_column(ForeignKey("copick_picks.id"))
    pick: Mapped["CopickPicks"] = relationship("CopickPicks", back_populates="points")


class CopickRun(Base):
    __tablename__ = "copick_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    meta: Mapped[Dict[str, Any]]

    # Parent Relationships
    voxel_spacings: Mapped["CopickVoxelSpacing"] = relationship("CopickVoxelSpacing", back_populates="run")
    picks: Mapped["CopickPicks"] = relationship("CopickPicks", back_populates="run")
    meshes: Mapped["CopickMesh"] = relationship("CopickMesh", back_populates="run")
    segmentations: Mapped["CopickSegmentation"] = relationship("CopickSegmentation", back_populates="run")


class CopickVoxelSpacing(Base):
    __tablename__ = "copick_voxel_spacings"

    # Self
    id: Mapped[int] = mapped_column(primary_key=True)
    voxel_size: Mapped[float]

    # Child Relationships
    run_id: Mapped[int] = mapped_column(ForeignKey("copick_runs.id"))
    run: Mapped["CopickRun"] = relationship("CopickRun", back_populates="voxel_spacings")

    # Parent Relationships
    tomograms: Mapped["CopickTomogram"] = relationship("CopickTomogram", back_populates="voxel_spacing")

    __table_args__ = (UniqueConstraint("run_id", "voxel_size", name="_run_voxel_size_uc"),)


class CopickTomogram(Base):
    __tablename__ = "copick_tomograms"

    # Self
    id: Mapped[int] = mapped_column(primary_key=True)
    tomo_type: Mapped[str]

    # Child Relationships
    voxel_spacing_id: Mapped[int] = mapped_column(ForeignKey("copick_voxel_spacings.id"))
    voxel_spacing: Mapped["CopickVoxelSpacing"] = relationship("CopickVoxelSpacing", back_populates="tomograms")

    # Parent Relationships
    features: Mapped["CopickFeatures"] = relationship("CopickFeatures", back_populates="tomogram")

    __table_args__ = (UniqueConstraint("voxel_spacing_id", "tomo_type", name="_voxel_spacing_tomo_type_uc"),)


class CopickFeatures(Base):
    __tablename__ = "copick_features"

    # Self
    id: Mapped[int] = mapped_column(primary_key=True)
    tomo_type: Mapped[str]
    feature_type: Mapped[str]

    # Child Relationships
    tomogram_id: Mapped[int] = mapped_column(ForeignKey("copick_tomograms.id"))
    tomogram: Mapped["CopickTomogram"] = relationship("CopickTomogram", back_populates="features")

    __table_args__ = (UniqueConstraint("tomogram_id", "feature_type", name="_tomogram_feature_uc"),)


class CopickPicks(Base):
    __tablename__ = "copick_picks"

    # Self
    id: Mapped[int] = mapped_column(primary_key=True)
    pickable_object_id: Mapped[int] = mapped_column(ForeignKey("pickable_objects.id"))
    pickable_object: Mapped["PickableObject"] = relationship("PickableObject")
    user_id: Mapped[str]
    session_id: Mapped[str]
    trust_orientation: Mapped[bool]

    # Child Relationships
    run_id: Mapped[int] = mapped_column(ForeignKey("copick_runs.id"))
    run: Mapped["CopickRun"] = relationship("CopickRun", back_populates="picks")

    # Parent Relationships
    points: Mapped["CopickPoint"] = relationship("CopickPoint")

    __table_args__ = (
        UniqueConstraint("pickable_object_id", "user_id", "session_id", "run_id", name="_pickable_user_session_run_uc"),
    )


class CopickMesh(Base):
    __tablename__ = "copick_meshes"

    # Self
    id: Mapped[int] = mapped_column(primary_key=True)
    pickable_object_id: Mapped[int] = mapped_column(ForeignKey("pickable_objects.id"))
    pickable_object: Mapped["PickableObject"] = relationship("PickableObject")
    user_id: Mapped[str]
    session_id: Mapped[str]

    # Child Relationships
    run_id: Mapped[int] = mapped_column(ForeignKey("copick_runs.id"))
    run: Mapped["CopickRun"] = relationship("CopickRun", back_populates="meshes")

    __table_args__ = (
        UniqueConstraint("pickable_object_id", "user_id", "session_id", "run_id", name="_pickable_user_session_run_uc"),
    )


class CopickSegmentation(Base):
    __tablename__ = "copick_segmentations"

    # Self
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str]
    session_id: Mapped[str]
    name: Mapped[str]
    is_multilabel: Mapped[bool]
    voxel_size: Mapped[float]

    run_id: Mapped[int] = mapped_column(ForeignKey("copick_runs.id"))
    run: Mapped["CopickRun"] = relationship("CopickRun", back_populates="segmentations")


if __name__ == "__main__":
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///test.db")
    Base.metadata.create_all(engine)

    import copick

    root = copick.from_file("/Users/utz.ermel/Documents/chlamy_proc/config/portal_config_demo.json")

    with Session(engine) as session:
        db_objects = []
        for o in root.pickable_objects:
            db_objects.append(
                PickableObject(
                    name=o.name,
                    label=o.label,
                    is_particle=o.is_particle,
                    color_red=o.color[0],
                    color_green=o.color[1],
                    color_blue=o.color[2],
                    color_alpha=o.color[3],
                    emdb_id=o.emdb_id,
                    pdb_id=o.pdb_id,
                    go_id=o.go_id,
                    map_threshold=o.map_threshold,
                    radius=o.radius,
                ),
            )

        session.add_all(db_objects)
        session.commit()

    with Session(engine) as session:
        from sqlalchemy import select

        query = select(PickableObject).where(PickableObject.name == "ribosome")
        print(list(session.execute(query)))
