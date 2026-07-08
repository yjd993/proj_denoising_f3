from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np
import plotly.graph_objects as go

try:
    from pyproj import Transformer
except ImportError:  # pragma: no cover - optional hover metadata only
    Transformer = None


def load_l3_points(l3_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    with h5py.File(l3_path, "r") as h5:
        northing = np.asarray(h5["POINT_X"][:], dtype=np.float64)
        easting = np.asarray(h5["POINT_Y"][:], dtype=np.float64)
        height = np.asarray(h5["POINT_Z"][:], dtype=np.float64)
        gnss_sec = np.asarray(h5["GNSS_SEC"][:], dtype=np.float64)

    finite = np.isfinite(easting) & np.isfinite(northing) & np.isfinite(height)
    return easting[finite], northing[finite], height[finite], gnss_sec[finite]


def sample_indices(count: int, sample_count: int, seed: int) -> np.ndarray:
    if count <= sample_count:
        return np.arange(count)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(count, size=sample_count, replace=False))


def write_ascii_ply(path: Path, easting: np.ndarray, northing: np.ndarray, height: np.ndarray) -> None:
    zmin = float(np.min(height))
    zrange = max(float(np.max(height) - zmin), 1e-9)
    colors = np.clip((height - zmin) / zrange * 255, 0, 255).astype(np.uint8)

    with path.open("w", encoding="ascii", newline="\n") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(easting)}\n")
        f.write("property double x\n")
        f.write("property double y\n")
        f.write("property double z\n")
        f.write("property uchar red\n")
        f.write("property uchar green\n")
        f.write("property uchar blue\n")
        f.write("end_header\n")
        for x, y, z, c in zip(easting, northing, height, colors):
            f.write(f"{x:.4f} {y:.4f} {z:.4f} {int(c)} {96} {int(255 - c)}\n")


def make_html(
    html_path: Path,
    easting: np.ndarray,
    northing: np.ndarray,
    height: np.ndarray,
    gnss_sec: np.ndarray,
) -> None:
    customdata = None
    hovertemplate = (
        "Easting: %{x:.3f} m<br>"
        "Northing: %{y:.3f} m<br>"
        "Height: %{z:.3f} m<br>"
        "GNSS sec: %{customdata[0]:.6f}"
        "<extra></extra>"
    )

    if Transformer is not None:
        transformer = Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(easting, northing)
        customdata = np.column_stack([gnss_sec, lon, lat])
        hovertemplate = (
            "Lon: %{customdata[1]:.8f}<br>"
            "Lat: %{customdata[2]:.8f}<br>"
            "Easting: %{x:.3f} m<br>"
            "Northing: %{y:.3f} m<br>"
            "Height: %{z:.3f} m<br>"
            "GNSS sec: %{customdata[0]:.6f}"
            "<extra></extra>"
        )
    else:
        customdata = np.column_stack([gnss_sec])

    fig = go.Figure(
        data=[
            go.Scatter3d(
                x=easting,
                y=northing,
                z=height,
                mode="markers",
                marker={
                    "size": 1.6,
                    "color": height,
                    "colorscale": "Viridis",
                    "opacity": 0.82,
                    "colorbar": {"title": "Height (m)", "thickness": 14},
                },
                customdata=customdata,
                hovertemplate=hovertemplate,
            )
        ]
    )
    fig.update_layout(
        title="0510_f3 L3 Geographic Point Cloud Preview",
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
        scene={
            "xaxis_title": "Easting (m, UTM 51N)",
            "yaxis_title": "Northing (m, UTM 51N)",
            "zaxis_title": "Height (m)",
            "aspectmode": "data",
        },
        template="plotly_white",
    )
    fig.write_html(html_path, include_plotlyjs=True, full_html=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a browsable L3 point cloud preview.")
    parser.add_argument(
        "--l3",
        type=Path,
        default=Path("0510_f3") / "L3_DATA" / "L2_cap_00111_20260510190957.h5",
        help="Input L3 HDF5 file containing POINT_X/Y/Z.",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("outputs") / "pointcloud_preview")
    parser.add_argument("--sample-count", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    easting, northing, height, gnss_sec = load_l3_points(args.l3)
    idx = sample_indices(len(easting), args.sample_count, args.seed)

    sample_e = easting[idx]
    sample_n = northing[idx]
    sample_h = height[idx]
    sample_t = gnss_sec[idx]

    html_path = args.out_dir / "0510_f3_l3_pointcloud_viewer.html"
    ply_path = args.out_dir / "0510_f3_l3_pointcloud_sample.ply"
    make_html(html_path, sample_e, sample_n, sample_h, sample_t)
    write_ascii_ply(ply_path, sample_e, sample_n, sample_h)

    print(f"Input points: {len(easting):,}")
    print(f"Sampled points: {len(sample_e):,}")
    print(f"HTML viewer: {html_path.resolve()}")
    print(f"PLY sample: {ply_path.resolve()}")


if __name__ == "__main__":
    main()
