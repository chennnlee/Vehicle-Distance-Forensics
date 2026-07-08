from __future__ import annotations

from pathlib import Path

import numpy as np


_PLY_SCALAR_DTYPES: dict[str, str] = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "i2",
    "int16": "i2",
    "ushort": "u2",
    "uint16": "u2",
    "int": "i4",
    "int32": "i4",
    "uint": "u4",
    "uint32": "u4",
    "float": "f4",
    "float32": "f4",
    "double": "f8",
    "float64": "f8",
}


def _to_plain_list(values: np.ndarray) -> list[float | int]:
    flat = np.asarray(values).reshape(-1)
    output: list[float | int] = []
    for value in flat:
        if np.issubdtype(flat.dtype, np.integer):
            output.append(int(value))
        else:
            output.append(float(value))
    return output


def _as_points_and_colors(array: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    if array.dtype.names is not None:
        names = set(array.dtype.names)
        if not {"x", "y", "z"}.issubset(names):
            raise ValueError("structured point cloud array must contain x, y, z fields")

        points = np.column_stack([array["x"], array["y"], array["z"]]).astype(np.float32, copy=False)

        if {"red", "green", "blue"}.issubset(names):
            colors = np.column_stack([array["red"], array["green"], array["blue"]]).astype(np.float32, copy=False)
            return points, _normalize_colors(colors)

        if {"r", "g", "b"}.issubset(names):
            colors = np.column_stack([array["r"], array["g"], array["b"]]).astype(np.float32, copy=False)
            return points, _normalize_colors(colors)

        if {"f_dc_0", "f_dc_1", "f_dc_2"}.issubset(names):
            dc = np.column_stack([array["f_dc_0"], array["f_dc_1"], array["f_dc_2"]]).astype(np.float32, copy=False)
            colors = np.clip(0.5 + 0.28209479177387814 * dc, 0.0, 1.0) * 255.0
            return points, colors.astype(np.float32, copy=False)

        return points, None

    points_array = np.asarray(array)
    if points_array.ndim == 1:
        points_array = points_array.reshape(1, -1)
    if points_array.ndim != 2 or points_array.shape[1] < 3:
        raise ValueError("point cloud array must have shape Nx3 or Nx6")

    points = points_array[:, :3].astype(np.float32, copy=False)
    colors = None
    if points_array.shape[1] >= 6:
        colors = _normalize_colors(points_array[:, 3:6].astype(np.float32, copy=False))
    return points, colors


def _normalize_colors(colors: np.ndarray) -> np.ndarray:
    if colors.size == 0:
        return colors.astype(np.float32, copy=False)

    colors = colors.astype(np.float32, copy=False)
    max_value = float(np.nanmax(colors)) if np.isfinite(colors).any() else 0.0
    if max_value <= 1.5:
        colors = colors * 255.0
    return np.clip(colors, 0.0, 255.0)


def _load_npz_point_cloud(path: Path) -> tuple[np.ndarray, np.ndarray | None]:
    with np.load(path, allow_pickle=False) as archive:
        for key in ("points", "xyz", "pointcloud", "pcd", "data"):
            if key in archive.files:
                points, colors = _as_points_and_colors(archive[key])
                break
        else:
            if len(archive.files) == 1:
                points, colors = _as_points_and_colors(archive[archive.files[0]])
            else:
                raise ValueError(f"{path} does not contain a supported point cloud array")

        if colors is None:
            if {"colors", "rgb"}.intersection(archive.files) and len(points):
                color_key = "colors" if "colors" in archive.files else "rgb"
                colors = _normalize_colors(np.asarray(archive[color_key]))
                if colors.ndim == 1:
                    colors = colors.reshape(-1, 3)
        return points, colors


def _load_ascii_ply(file_handle, vertex_count: int, property_names: list[str]) -> np.ndarray:
    if vertex_count <= 0:
        return np.empty((0, len(property_names)), dtype=np.float32)

    data = np.loadtxt(file_handle, max_rows=vertex_count)
    if data.ndim == 1:
        if len(property_names) == 1 and vertex_count > 1:
            data = data.reshape(-1, 1)
        else:
            data = data.reshape(1, -1)
    if data.shape[1] < len(property_names):
        raise ValueError("ASCII PLY vertex data has fewer columns than the header declares")
    return np.asarray(data[:, : len(property_names)], dtype=np.float32)


def _load_binary_ply(file_handle, vertex_count: int, property_types: list[tuple[str, str]], endian_prefix: str) -> np.ndarray:
    dtype_fields = []
    for name, ply_type in property_types:
        np_dtype = _PLY_SCALAR_DTYPES.get(ply_type)
        if np_dtype is None:
            raise ValueError(f"Unsupported PLY property type: {ply_type}")
        dtype_fields.append((name, np.dtype(endian_prefix + np_dtype)))

    if vertex_count <= 0:
        return np.empty((0, len(dtype_fields)), dtype=np.float32)

    structured = np.fromfile(file_handle, dtype=np.dtype(dtype_fields), count=vertex_count)
    data = np.column_stack([structured[name] for name, _ in property_types]).astype(np.float32, copy=False)
    return data


def _parse_sharp_metadata(raw_metadata: dict[str, list[float | int]]) -> dict[str, object]:
    metadata: dict[str, object] = {}

    image_size = raw_metadata.get("image_size")
    if image_size is not None and len(image_size) >= 2:
        metadata["image_size"] = {"width": int(image_size[0]), "height": int(image_size[1])}

    intrinsic = raw_metadata.get("intrinsic")
    if intrinsic is not None:
        if len(intrinsic) == 9:
            k = np.asarray(intrinsic, dtype=np.float32).reshape(3, 3)
            metadata["intrinsics"] = {
                "fx": float(k[0, 0]),
                "fy": float(k[1, 1]),
                "cx": float(k[0, 2]),
                "cy": float(k[1, 2]),
                "source": "ply_intrinsic_3x3",
            }
        elif len(intrinsic) == 4:
            metadata["intrinsics"] = {
                "fx": float(intrinsic[0]),
                "fy": float(intrinsic[1]),
                "cx": None,
                "cy": None,
                "source": "ply_intrinsic_legacy",
            }
            metadata["image_size"] = {"width": int(intrinsic[2]), "height": int(intrinsic[3])}

    if "extrinsic" in raw_metadata:
        metadata["extrinsic"] = raw_metadata["extrinsic"]
    if "disparity" in raw_metadata:
        metadata["disparity"] = raw_metadata["disparity"]
    if "version" in raw_metadata:
        metadata["version"] = raw_metadata["version"]
    return metadata


def _load_ply_point_cloud(path: Path) -> tuple[np.ndarray, np.ndarray | None, dict[str, object]]:
    format_name = None
    vertex_count = None
    property_names: list[str] = []
    property_types: list[tuple[str, str]] = []
    element_specs: list[dict[str, object]] = []
    current_element: dict[str, object] | None = None

    with path.open("rb") as file_handle:
        first_line = file_handle.readline().decode("ascii", errors="strict").strip()
        if first_line != "ply":
            raise ValueError(f"{path} is not a PLY file")

        while True:
            raw_line = file_handle.readline()
            if not raw_line:
                raise ValueError(f"Unexpected end of header in {path}")
            line = raw_line.decode("ascii", errors="strict").strip()
            if line == "end_header":
                break
            if not line or line.startswith("comment") or line.startswith("obj_info"):
                continue

            tokens = line.split()
            keyword = tokens[0]

            if keyword == "format":
                format_name = tokens[1]
                continue

            if keyword == "element":
                element_name = tokens[1]
                current_element = {
                    "name": element_name,
                    "count": int(tokens[2]),
                    "properties": [],
                }
                element_specs.append(current_element)
                if element_name == "vertex":
                    vertex_count = int(tokens[2])
                continue

            if keyword == "property":
                if current_element is None:
                    raise ValueError(f"PLY property appears before element in {path}")
                if tokens[1] == "list":
                    raise ValueError("PLY list properties are not supported")
                properties = current_element["properties"]
                assert isinstance(properties, list)
                properties.append((tokens[2], tokens[1]))
                if current_element["name"] == "vertex":
                    property_types.append((tokens[2], tokens[1]))
                    property_names.append(tokens[2])

        if format_name is None:
            raise ValueError(f"PLY format is missing in {path}")
        if vertex_count is None:
            raise ValueError(f"PLY vertex element is missing in {path}")
        if not property_names:
            raise ValueError(f"PLY vertex properties are missing in {path}")

        vertex_data = None
        raw_metadata: dict[str, list[float | int]] = {}
        for spec in element_specs:
            spec_name = str(spec["name"])
            spec_count = int(spec["count"])
            spec_properties = spec["properties"]
            assert isinstance(spec_properties, list)
            spec_property_types = [(str(name), str(dtype)) for name, dtype in spec_properties]
            spec_property_names = [name for name, _ in spec_property_types]

            if format_name == "ascii":
                element_data = _load_ascii_ply(file_handle, spec_count, spec_property_names)
            elif format_name == "binary_little_endian":
                element_data = _load_binary_ply(file_handle, spec_count, spec_property_types, "<")
            elif format_name == "binary_big_endian":
                element_data = _load_binary_ply(file_handle, spec_count, spec_property_types, ">")
            else:
                raise ValueError(f"Unsupported PLY format: {format_name}")

            if spec_name == "vertex":
                vertex_data = element_data
            elif spec_property_names:
                raw_metadata[spec_name] = _to_plain_list(element_data)

    if vertex_data is None:
        raise ValueError(f"PLY vertex data is missing in {path}")

    column_index = {name: idx for idx, name in enumerate(property_names)}
    if not {"x", "y", "z"}.issubset(column_index):
        raise ValueError(f"{path} does not contain x/y/z vertex properties")

    points = vertex_data[:, [column_index["x"], column_index["y"], column_index["z"]]].astype(np.float32, copy=False)

    colors = None
    if {"red", "green", "blue"}.issubset(column_index):
        colors = vertex_data[:, [column_index["red"], column_index["green"], column_index["blue"]]]
    elif {"r", "g", "b"}.issubset(column_index):
        colors = vertex_data[:, [column_index["r"], column_index["g"], column_index["b"]]]
    elif {"f_dc_0", "f_dc_1", "f_dc_2"}.issubset(column_index):
        dc = vertex_data[:, [column_index["f_dc_0"], column_index["f_dc_1"], column_index["f_dc_2"]]]
        colors = np.clip(0.5 + 0.28209479177387814 * dc, 0.0, 1.0) * 255.0

    if colors is not None:
        colors = _normalize_colors(colors)

    return points, colors, _parse_sharp_metadata(raw_metadata)


def load_point_cloud_points(path: str | Path) -> tuple[np.ndarray, np.ndarray | None, dict[str, object]]:
    """Load a point cloud from common local formats.

    Returns points as an Nx3 float32 array and optional RGB colors as Nx3 float32.
    The function supports .ply, .npy, .npz, .xyz, .txt, and .csv files.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"point cloud file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".ply":
        points, colors, extra_metadata = _load_ply_point_cloud(path)
        source_format = "ply"
    elif suffix == ".npy":
        points, colors = _as_points_and_colors(np.load(path, allow_pickle=False))
        source_format = "npy"
        extra_metadata = {}
    elif suffix == ".npz":
        points, colors = _load_npz_point_cloud(path)
        source_format = "npz"
        extra_metadata = {}
    elif suffix in {".xyz", ".txt"}:
        data = np.loadtxt(path)
        points, colors = _as_points_and_colors(data)
        source_format = suffix.lstrip(".")
        extra_metadata = {}
    elif suffix == ".csv":
        data = np.loadtxt(path, delimiter=",")
        points, colors = _as_points_and_colors(data)
        source_format = "csv"
        extra_metadata = {}
    else:
        raise ValueError(f"unsupported point cloud format: {path.suffix}")

    metadata: dict[str, object] = {
        "path": str(path),
        "format": source_format,
        "point_count": int(points.shape[0]),
        "has_colors": bool(colors is not None),
    }
    metadata.update(extra_metadata)
    return points.astype(np.float32, copy=False), None if colors is None else colors.astype(np.float32, copy=False), metadata
