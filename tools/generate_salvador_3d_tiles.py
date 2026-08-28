"""Generate static Mapbox Vector Tiles for Salvador GBA LoD1 buildings.

The source GBA geometry parquet and the derived metrics parquet have identical
row order.  The metrics file supplies the 50 m grid keys used to join each
building to the model output in the Salvador GeoPackage.
"""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import mapbox_vector_tile
import numpy as np
import pyarrow.parquet as pq
import shapely
from mapbox_vector_tile.encoder import on_invalid_geometry_make_valid


ZOOM = 15
EXTENT = 4096
CLASS_MAP = {
    "prioridade": "priority",
    "atencao": "attention",
    "outros": "other",
    "fcu_mapeada": "mappedFcu",
    "fcu_revisao": "mappedLow",
}
MODEL_MAP = {
    "completo": "complete",
    "morfologico": "morphological",
    "nao_morfologico": "non_morphological",
}


def tile_xy(lon: np.ndarray, lat: np.ndarray, zoom: int = ZOOM) -> tuple[np.ndarray, np.ndarray]:
    scale = 1 << zoom
    clipped_lat = np.clip(lat, -85.05112878, 85.05112878)
    x = np.floor((lon + 180.0) / 360.0 * scale).astype(np.int32)
    rad = np.radians(clipped_lat)
    y = np.floor((1.0 - np.arcsinh(np.tan(rad)) / math.pi) / 2.0 * scale).astype(np.int32)
    return x, y


def tile_bounds(x: int, y: int, zoom: int = ZOOM) -> tuple[float, float, float, float]:
    scale = 1 << zoom
    west = x / scale * 360.0 - 180.0
    east = (x + 1) / scale * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / scale))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (y + 1) / scale))))
    return west, south, east, north


def load_cells(gpkg: Path) -> tuple[dict[int, dict[str, object]], set[int]]:
    columns = [
        "ID",
        "id_col",
        "id_row",
        "winner_scenario",
        "prob_fcu_winner",
        "classe_candidato_winner",
    ]
    cells = gpd.read_file(gpkg, layer="predicoes_base0407", columns=columns)
    centroids = cells.geometry.centroid
    lookup: dict[int, dict[str, object]] = {}
    keys: set[int] = set()
    for row, lon, lat in zip(cells.itertuples(index=False), centroids.x, centroids.y, strict=True):
        key = int(row.id_col) * 20_000_000 + int(row.id_row)
        keys.add(key)
        lookup[key] = {
            "cell_id": str(row.ID),
            "cell_lat": round(float(lat), 7),
            "cell_lng": round(float(lon), 7),
            "class": CLASS_MAP.get(str(row.classe_candidato_winner), "unmodeled"),
            "probability": round(float(row.prob_fcu_winner), 6),
            "winning_model": MODEL_MAP.get(str(row.winner_scenario), str(row.winner_scenario)),
        }
    return lookup, keys


def collect_buildings(
    geometry_parquet: Path,
    metrics_parquet: Path,
    cell_keys: set[int],
    batch_size: int = 65_536,
) -> tuple[list[object], np.ndarray, np.ndarray]:
    geometry_file = pq.ParquetFile(geometry_parquet)
    metrics_file = pq.ParquetFile(metrics_parquet)
    if geometry_file.metadata.num_rows != metrics_file.metadata.num_rows:
        raise RuntimeError("GBA geometry and metrics row counts differ")

    geometries: list[object] = []
    heights: list[float] = []
    matched_keys: list[int] = []
    geometry_batches = geometry_file.iter_batches(batch_size=batch_size, columns=["height", "geometry"])
    metrics_batches = metrics_file.iter_batches(batch_size=batch_size, columns=["id_col_50", "id_row_50"])

    processed = 0
    for geometry_batch, metrics_batch in zip(geometry_batches, metrics_batches, strict=True):
        if geometry_batch.num_rows != metrics_batch.num_rows:
            raise RuntimeError("GBA geometry and metrics batches lost row alignment")
        cols = metrics_batch.column(0).to_numpy(zero_copy_only=False).astype(np.int64, copy=False)
        rows = metrics_batch.column(1).to_numpy(zero_copy_only=False).astype(np.int64, copy=False)
        keys = cols * 20_000_000 + rows
        mask = np.fromiter((int(key) in cell_keys for key in keys), dtype=bool, count=len(keys))
        if mask.any():
            selected_wkb = geometry_batch.column(1).to_numpy(zero_copy_only=False)[mask]
            selected_geometries = shapely.from_wkb(selected_wkb, on_invalid="ignore")
            selected_heights = geometry_batch.column(0).to_numpy(zero_copy_only=False)[mask]
            valid = (~shapely.is_missing(selected_geometries)) & (~shapely.is_empty(selected_geometries))
            geometries.extend(selected_geometries[valid].tolist())
            heights.extend(np.nan_to_num(selected_heights[valid], nan=0.0).astype(float).tolist())
            matched_keys.extend(keys[mask][valid].astype(np.int64).tolist())
        processed += geometry_batch.num_rows
        if processed % (batch_size * 16) == 0 or processed == geometry_file.metadata.num_rows:
            print(f"scanned={processed:,} matched={len(geometries):,}", flush=True)

    return geometries, np.asarray(heights), np.asarray(matched_keys, dtype=np.int64)


def write_tiles(
    output_dir: Path,
    geometries: list[object],
    heights: np.ndarray,
    matched_keys: np.ndarray,
    cell_lookup: dict[int, dict[str, object]],
) -> None:
    geometry_array = np.asarray(geometries, dtype=object)
    centers = shapely.centroid(geometry_array)
    xs, ys = tile_xy(shapely.get_x(centers), shapely.get_y(centers))
    tile_rows: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, tile_x, tile_y in zip(range(len(geometry_array)), xs, ys, strict=True):
        tile_rows[(int(tile_x), int(tile_y))].append(index)

    total_bytes = 0
    for number, ((tile_x, tile_y), indices) in enumerate(sorted(tile_rows.items()), start=1):
        features = []
        for index in indices:
            properties = dict(cell_lookup[int(matched_keys[index])])
            properties["height"] = round(max(0.0, float(heights[index])), 2)
            features.append({"geometry": geometry_array[index], "properties": properties})
        payload = mapbox_vector_tile.encode(
            {"name": "buildings", "features": features},
            default_options={
                "quantize_bounds": tile_bounds(tile_x, tile_y),
                "extents": EXTENT,
                "on_invalid_geometry": on_invalid_geometry_make_valid,
            },
        )
        destination = output_dir / str(ZOOM) / str(tile_x) / f"{tile_y}.pbf.gz"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        total_bytes += len(payload)
        if number % 50 == 0 or number == len(tile_rows):
            print(
                f"tiles={number:,}/{len(tile_rows):,} bytes={total_bytes / 1024 / 1024:.1f} MiB",
                flush=True,
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry-parquet", type=Path, required=True)
    parser.add_argument("--metrics-parquet", type=Path, required=True)
    parser.add_argument("--gpkg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cell_lookup, cell_keys = load_cells(args.gpkg)
    print(f"model_cells={len(cell_keys):,}", flush=True)
    geometries, heights, matched_keys = collect_buildings(
        args.geometry_parquet, args.metrics_parquet, cell_keys
    )
    print(f"matched_buildings={len(geometries):,}", flush=True)
    write_tiles(args.output, geometries, heights, matched_keys, cell_lookup)


if __name__ == "__main__":
    main()
