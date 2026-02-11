# Geometry Conventions

This document describes the mathematical conventions used in copick for representing spatial data, including point
positions, orientations, volumetric data, and meshes. Understanding these conventions is essential for correctly
interpreting data, implementing new tools, and ensuring interoperability with other cryo-ET software packages.

## Overview

Cryo-electron tomography (cryo-ET) data involves multiple coordinate systems and representations: physical coordinates
in Angstroms, voxel indices in 3D arrays, and transformation matrices describing particle orientations. Different
software packages in the cryo-ET ecosystem use varying conventions for these representations, which can lead to
confusion and errors when exchanging data.

Copick adopts a set of conventions designed to be internally consistent and to facilitate conversion to and from other
common formats (RELION, Dynamo, TOM/Artiatomi). This document provides a rigorous mathematical description of these
conventions.

---

## 1. Coordinate System

### 1.1 Physical Coordinates

All spatial positions in copick are expressed in **physical coordinates** with the following properties:

| Property | Value |
|----------|-------|
| **Units** | Angstrom (Å) |
| **Origin** | Corner of the tomogram volume (0, 0, 0) |
| **Indexing** | 0-indexed |
| **Handedness** | Right-handed |

A point in physical space is represented as a 3-vector:

$$\mathbf{p} = (x, y, z) \in \mathbb{R}^3$$

where $x$, $y$, and $z$ are distances in Angstrom measured from the corner of the tomogram volume along each respective
axis.

### 1.2 Voxel Coordinates

Voxel coordinates are integer indices into a 3D array. The relationship between voxel and physical coordinates is
mediated by the **voxel spacing** $s$ (in Å/voxel):

$$\mathbf{p}_\text{physical} = \mathbf{p}_\text{voxel} \cdot s$$

$$\mathbf{p}_\text{voxel} = \left\lfloor \frac{\mathbf{p}_\text{physical}}{s} \right\rfloor$$

where the floor operation is used when converting continuous physical coordinates to discrete voxel indices.

---

## 2. Pick Geometry

Picks represent point annotations in a tomogram, typically marking the locations and orientations of particles or other
structures of interest.

### 2.1 Position

Pick positions are stored as `CopickLocation(x, y, z)` objects containing physical coordinates in Angstrom. The position
represents the center of the picked object in tomogram space.

```python
class CopickLocation:
    x: float  # Angstrom
    y: float  # Angstrom
    z: float  # Angstrom
```

### 2.2 Orientation (Transformation Matrix)

Each pick has an associated 4×4 homogeneous affine transformation matrix $\mathbf{T}$ that describes the orientation
of the particle. This matrix transforms coordinates **from object space to tomogram space**:

$$\mathbf{T} = \begin{pmatrix}
r_{00} & r_{01} & r_{02} & t_x \\
r_{10} & r_{11} & r_{12} & t_y \\
r_{20} & r_{21} & r_{22} & t_z \\
0 & 0 & 0 & 1
\end{pmatrix}$$

where:

- $\mathbf{R} = (r_{ij})_{i,j \in \{0,1,2\}}$ is a 3×3 rotation matrix in SO(3)
- $\mathbf{t} = (t_x, t_y, t_z)^T$ is the translation component in Angstrom

#### Interpretation

The transformation matrix answers the question: *"If I have a point defined in the particle's local coordinate frame,
where does it appear in the tomogram?"*

For a point $\mathbf{p}_\text{obj}$ in object space, the corresponding point in tomogram space is:

$$\mathbf{p}_\text{tomo} = \mathbf{T} \cdot \mathbf{p}_\text{obj}$$

In homogeneous coordinates:

$$\begin{pmatrix} p'_x \\ p'_y \\ p'_z \\ 1 \end{pmatrix} = \mathbf{T} \cdot \begin{pmatrix} p_x \\ p_y \\ p_z \\ 1 \end{pmatrix}$$

#### Constraints

The transformation matrix must satisfy:

1. The bottom row must be $(0, 0, 0, 1)$
2. The element $\mathbf{T}_{3,3} = 1$
3. The rotation submatrix $\mathbf{R}$ should be orthonormal (i.e., $\mathbf{R}^T \mathbf{R} = \mathbf{I}$ and
   $\det(\mathbf{R}) = 1$)

#### Default Value

For picks without orientation information, the identity matrix is used:

$$\mathbf{T}_\text{default} = \mathbf{I}_4 = \begin{pmatrix}
1 & 0 & 0 & 0 \\
0 & 1 & 0 & 0 \\
0 & 0 & 1 & 0 \\
0 & 0 & 0 & 1
\end{pmatrix}$$

### 2.3 Relationship Between Position and Transform

The pick's `location` field stores the position of the particle center in tomogram coordinates. The `transformation`
matrix describes the particle's orientation and may contain an additional translation component (e.g., for refined
shifts during subtomogram averaging).

The **full position** of the particle center, including any refinement shifts, is:

$$\mathbf{p}_\text{full} = \mathbf{p}_\text{location} + \mathbf{t}_\text{transform}$$

where $\mathbf{t}_\text{transform} = (t_x, t_y, t_z)^T$ is extracted from the transformation matrix.

---

## 3. Volume Geometry (Tomograms and Segmentations)

Volumetric data in copick includes tomograms (3D reconstructions) and segmentations (labeled volumes).

### 3.1 Array Axis Ordering

Volumes are stored in **ZYX axis order**, following the C-contiguous (row-major) convention standard in Python/NumPy:

```python
array[z, y, x]  # Python/NumPy indexing
```

For a volume with dimensions $(N_z, N_y, N_x)$:

- The first axis (index 0) corresponds to the **Z** dimension
- The second axis (index 1) corresponds to the **Y** dimension
- The third axis (index 2) corresponds to the **X** dimension

This ordering is reflected in the OME-Zarr metadata, which specifies axes as `["z", "y", "x"]` with units in Angstrom.

### 3.2 Voxel-to-Physical Coordinate Mapping

For a voxel at array index $(i_z, i_y, i_x)$, the physical coordinates are:

$$\mathbf{p}_\text{physical} = (x, y, z) = (i_x \cdot s, \quad i_y \cdot s, \quad i_z \cdot s)$$

where $s$ is the isotropic voxel spacing in Å/voxel.

!!! warning "Axis Order Mismatch"
    Note the difference between array indexing order `[z, y, x]` and physical coordinate order `(x, y, z)`. This is a
    common source of bugs when converting between representations.

### 3.3 OME-Zarr Scale Transform

The OME-Zarr format stores coordinate transforms as part of the metadata. For copick volumes, the scale transform is:

$$\mathbf{S} = \text{diag}(s_z, s_y, s_x) = \text{diag}(s, s, s)$$

This transform maps voxel indices to physical coordinates:

$$\mathbf{p}_\text{physical} = \mathbf{S} \cdot \mathbf{p}_\text{voxel}$$

where the vectors follow the ZYX ordering convention.

### 3.4 Multiscale Pyramids

Tomograms and segmentations are stored as multiscale pyramids with successive 2× downsampling. The available resolution
levels are typically:

| Level | Scale Factor | Voxel Spacing |
|-------|--------------|---------------|
| `"0"` | 1× | $s$ |
| `"1"` | 2× | $2s$ |
| `"2"` | 4× | $4s$ |

For a voxel at index $\mathbf{i}$ in level $n$, the corresponding index in level $0$ is approximately:

$$\mathbf{i}_0 \approx 2^n \cdot \mathbf{i}_n$$

---

## 4. Mesh Geometry

Meshes in copick represent surface annotations, typically for structures like membranes, organelles, or sample
boundaries.

### 4.1 Vertex Coordinates

Mesh vertices are stored in **physical coordinates** (Angstrom), consistent with pick positions:

$$\mathbf{V} = \{\mathbf{v}_i\}_{i=1}^{N}, \quad \mathbf{v}_i = (x_i, y_i, z_i) \in \mathbb{R}^3$$

The coordinate system matches that of picks and tomograms: corner-origin, 0-indexed, in Angstrom.

### 4.2 Storage Format

Meshes are stored in **GLB format** (binary glTF), which is a widely-supported 3D format that efficiently stores
vertices, faces, and optional attributes like normals and colors.

### 4.3 Mesh-Volume Correspondence

To find the voxel containing a mesh vertex:

$$\mathbf{i}_\text{voxel} = \left\lfloor \frac{\mathbf{v}_\text{physical}}{s} \right\rfloor$$

To sample the volume value at a vertex position (with interpolation), use the continuous voxel coordinates:

$$\mathbf{i}_\text{continuous} = \frac{\mathbf{v}_\text{physical}}{s}$$

---

## 5. Euler Angle Conventions for Import/Export

When exchanging data with other cryo-ET software, coordinate and rotation conventions must be carefully converted.
Copick stores rotations as 3×3 matrices, but other formats often use Euler angles.

### 5.1 Convention Summary

| Format | Euler Convention | Rotation Type | Notes |
|--------|------------------|---------------|-------|
| **RELION** | ZYZ | Extrinsic, inverted | Uses `rlnAngleRot`, `rlnAngleTilt`, `rlnAnglePsi` |
| **Dynamo** | ZXZ | Intrinsic, inverted | Uses `tdrot`, `tilt`, `narot` |
| **TOM/Artiatomi** | ZXZ | Intrinsic | Uses $\phi$, $\theta$, $\psi$ (stored as $\phi$, $\psi$, $\theta$ in file) |
| **Copick (native)** | Matrix | N/A | Full 4×4 transformation matrix |

### 5.2 Conversion Formulas

#### RELION to Copick

Given RELION Euler angles $(\phi, \theta, \psi)$ in ZYZ convention:

$$\mathbf{R} = \left( R_z(\phi) \cdot R_y(\theta) \cdot R_z(\psi) \right)^{-1}$$

where $R_z$ and $R_y$ are elementary rotation matrices about the Z and Y axes, respectively.

#### Dynamo to Copick

Given Dynamo Euler angles $(t_\text{drot}, t_\text{ilt}, n_\text{arot})$ in ZXZ convention:

$$\mathbf{R} = \left( R_z(t_\text{drot}) \cdot R_x(t_\text{ilt}) \cdot R_z(n_\text{arot}) \right)^{-1}$$

Note: Lowercase convention letters (e.g., `zxz`) indicate intrinsic rotations in scipy.

#### TOM/Artiatomi to Copick

Given TOM Euler angles $(\phi, \theta, \psi)$ in ZXZ convention:

$$\mathbf{R} = R_z(\phi) \cdot R_x(\theta) \cdot R_z(\psi)$$

No inversion is applied for the TOM format.

### 5.3 Position Convention Summary

| Format | Position Units | Origin | Indexing |
|--------|----------------|--------|----------|
| **Copick (native)** | Angstrom | Corner | 0-indexed |
| **Dynamo** | Pixels | Corner | 0-indexed |
| **TOM/Artiatomi** | Pixels | Corner | 1-indexed (converted on read) |
| **RELION** | Pixels or Angstrom | Centered or Corner | 0-indexed |
| **CSV** | Angstrom | Corner | 0-indexed |

---

## 6. Summary and Quick Reference

### Key Points

1. **All spatial data uses Angstrom units** - Positions, mesh vertices, and transformation translations are all in
   Angstrom.

2. **Corner-origin, 0-indexed** - The coordinate origin is at the corner of the tomogram, and indices start at 0.

3. **Volumes use ZYX ordering** - Array indexing is `[z, y, x]`, but physical coordinates are `(x, y, z)`.

4. **Transformations go from object to tomogram space** - The transformation matrix $\mathbf{T}$ maps points in the
   particle's local frame to the tomogram coordinate system.

5. **Voxel spacing is isotropic** - Copick assumes equal spacing in all three dimensions.

### Common Conversions

| From | To | Formula |
|------|----|---------|
| Physical (Å) | Voxel | $\mathbf{p}_\text{voxel} = \lfloor \mathbf{p}_\text{Å} / s \rfloor$ |
| Voxel | Physical (Å) | $\mathbf{p}_\text{Å} = \mathbf{p}_\text{voxel} \cdot s$ |
| Object space | Tomogram space | $\mathbf{p}_\text{tomo} = \mathbf{T} \cdot \mathbf{p}_\text{obj}$ |
| Array index `[z,y,x]` | Physical `(x,y,z)` | $(x, y, z) = (i_x \cdot s, i_y \cdot s, i_z \cdot s)$ |
