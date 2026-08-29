"""Reclassify the legacy remote GBA tiles with the current action ranking.

The remote 3D deployments predate the action ladder and still contain classes
such as ``mappedFcu`` and ``mappedLow``.  Those labels describe territorial
status, not action priority.  This utility preserves every building geometry
and height, replacing only its action class from the current per-area ranking.
FCU polygons remain a separate layer in the viewer.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import requests
import shapely
from mapbox_vector_tile.Mapbox import vector_tile_pb2


ZOOM = 15
GROUPS = {
    "sp": {
        "project": "preditor-fcu-3d-sp",
        "origin": "https://preditor-fcu-3d-sp.vercel.app",
        "areas": ["area_conc_urb_sao_paulo"],
    },
    "rj": {
        "project": "preditor-fcu-3d-rj",
        "origin": "https://preditor-fcu-3d-rj.vercel.app",
        "areas": [
            "area_arranjo_pop_rj",
            "area_conc_urb_rio_de_janeiro",
            "area_medias_conc_urb_rj",
        ],
    },
    "centro": {
        "project": "preditor-fcu-3d-centro",
        "origin": "https://preditor-fcu-3d-centro.vercel.app",
        "areas": [
            "area_conc_urb_curitiba",
            "area_conc_urb_fortaleza",
            "area_conc_urb_goiania",
        ],
    },
    "norte": {
        "project": "preditor-fcu-3d-norte",
        "origin": "https://preditor-fcu-3d-norte.vercel.app",
        "areas": ["area_rgint_belem", "area_rgint_macapa", "area_rgint_redencao"],
    },
}

_thread_local = threading.local()


def session() -> requests.Session:
    current = getattr(_thread_local, "session", None)
    if current is None:
        current = requests.Session()
        current.headers["User-Agent"] = "Preditor-FCU-3D-tile-migration/1.0"
        _thread_local.session = current
    return current


def tile_xy(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    scale = 1 << ZOOM
    clipped_lat = np.clip(lat, -85.05112878, 85.05112878)
    x = np.floor((lon + 180.0) / 360.0 * scale).astype(np.int32)
    rad = np.radians(clipped_lat)
    y = np.floor((1.0 - np.arcsinh(np.tan(rad)) / math.pi) / 2.0 * scale).astype(np.int32)
    return x, y


def area_parquet(products_root: Path, area: str) -> Path:
    matches = sorted((products_root / area).glob("*.geoparquet"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one GeoParquet for {area}; found {len(matches)}")
    return matches[0]


def load_area_lookup(
    parquet_path: Path, priority_limit: int, attention_limit: int
) -> tuple[dict[str, str], set[tuple[int, int]], Counter]:
    table = pq.read_table(
        parquet_path,
        columns=[
            "ID",
            "ranking_total_winner",
            "target",
            "geometry",
        ],
    )
    cell_ids = table.column("ID").to_pylist()
    ranks = table.column("ranking_total_winner").to_numpy(zero_copy_only=False)
    targets = table.column("target").to_numpy(zero_copy_only=False)

    classes = np.full(len(ranks), "other", dtype=object)
    classes[ranks <= attention_limit] = "attention"
    classes[ranks <= priority_limit] = "priority"
    lookup = {
        str(cell_id): str(action)
        for cell_id, action in zip(cell_ids, classes, strict=True)
    }

    geometries = shapely.from_wkb(table.column("geometry").to_numpy(zero_copy_only=False))
    centroids = shapely.centroid(geometries)
    xs, ys = tile_xy(shapely.get_x(centroids), shapely.get_y(centroids))
    core_tiles = {(int(x), int(y)) for x, y in zip(xs, ys, strict=True)}
    candidate_tiles = {
        (x + dx, y + dy)
        for x, y in core_tiles
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
    }
    audit = Counter(classes.tolist())
    audit["cells"] = len(cell_ids)
    audit["fcu_cells"] = int(np.count_nonzero(targets == 1))
    audit["core_tiles"] = len(core_tiles)
    audit["candidate_tiles"] = len(candidate_tiles)
    return lookup, candidate_tiles, audit


def fetch_and_reclassify(
    origin: str,
    area: str,
    tile: tuple[int, int],
    lookup: dict[str, str],
    timeout: float,
) -> tuple[tuple[int, int], bytes | None, Counter]:
    x, y = tile
    url = f"{origin}/areas/{area}/tiles/{ZOOM}/{x}/{y}.pbf.gz"
    response = session().get(url, timeout=timeout, stream=True)
    if response.status_code == 404:
        response.close()
        return tile, None, Counter(tiles_missing=1)
    response.raise_for_status()
    response.raw.decode_content = False
    raw_payload = response.raw.read()
    response.close()
    if raw_payload.startswith(b"\x1f\x8b"):
        raw_payload = gzip.decompress(raw_payload)

    tile_message = vector_tile_pb2.tile()
    tile_message.ParseFromString(raw_payload)
    layer = next((item for item in tile_message.layers if item.name == "buildings"), None)
    if layer is None:
        raise RuntimeError(f"Tile without buildings layer: {url}")
    features = layer.features
    if not features:
        return tile, None, Counter(tiles_empty=1)
    counts = Counter(tiles_found=1, buildings=len(features))

    if "class" not in layer.keys:
        layer.keys.append("class")
    class_key_index = list(layer.keys).index("class")
    cell_key_index = (
        list(layer.keys).index("cell_id") if "cell_id" in layer.keys else None
    )

    class_value_indices: dict[str, int] = {}
    for action in ("priority", "attention", "other"):
        value_index = next(
            (
                index
                for index, value in enumerate(layer.values)
                if value.HasField("string_value") and value.string_value == action
            ),
            None,
        )
        if value_index is None:
            value = layer.values.add()
            value.string_value = action
            value_index = len(layer.values) - 1
        class_value_indices[action] = value_index

    geometry_command_count = sum(len(feature.geometry) for feature in features)
    geometry_samples = {
        index: tuple(features[index].geometry)
        for index in {0, len(features) // 2, len(features) - 1}
        if features
    }
    for feature in features:
        cell_id = ""
        class_tag_position = None
        old_action = ""
        for tag_position in range(0, len(feature.tags), 2):
            key_index = feature.tags[tag_position]
            value_index = feature.tags[tag_position + 1]
            if cell_key_index is not None and key_index == cell_key_index:
                value = layer.values[value_index]
                if value.HasField("string_value"):
                    cell_id = value.string_value
            elif key_index == class_key_index:
                class_tag_position = tag_position + 1
                value = layer.values[value_index]
                if value.HasField("string_value"):
                    old_action = value.string_value
        if class_tag_position is None:
            feature.tags.extend([class_key_index, class_value_indices["other"]])
            class_tag_position = len(feature.tags) - 1
        action = lookup.get(cell_id)
        if action is None:
            action = "other"
            counts["buildings_without_cell"] += 1
        if old_action != action:
            counts["buildings_changed"] += 1
        feature.tags[class_tag_position] = class_value_indices[action]
        counts[action] += 1

    encoded = tile_message.SerializeToString()
    verified_message = vector_tile_pb2.tile()
    verified_message.ParseFromString(encoded)
    verified_layer = next(
        (item for item in verified_message.layers if item.name == "buildings"), None
    )
    if verified_layer is None or len(verified_layer.features) != len(features):
        raise RuntimeError(f"Feature count changed while encoding {url}")
    if sum(len(feature.geometry) for feature in verified_layer.features) != geometry_command_count:
        raise RuntimeError(f"Geometry command count changed while encoding {url}")
    for index, geometry in geometry_samples.items():
        if tuple(verified_layer.features[index].geometry) != geometry:
            raise RuntimeError(f"Sample geometry changed while encoding {url}")
    return tile, encoded, counts


def write_vercel_config(destination: Path) -> None:
    config = {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "cleanUrls": True,
        "trailingSlash": False,
        "headers": [
            {
                "source": "/areas/(.*)/tiles/(.*).pbf.gz",
                "headers": [
                    {
                        "key": "Content-Type",
                        "value": "application/vnd.mapbox-vector-tile",
                    },
                    {
                        "key": "Cache-Control",
                        "value": "public, max-age=31536000, immutable",
                    },
                    {"key": "Access-Control-Allow-Origin", "value": "*"},
                ],
            }
        ],
    }
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "vercel.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (destination / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Preditor FCU 3D tiles</title>\n",
        encoding="utf-8",
    )


def process_area(
    *,
    area: str,
    origin: str,
    products_root: Path,
    rules: dict,
    destination: Path,
    workers: int,
    timeout: float,
) -> dict:
    rule = rules[area]
    lookup, candidates, cell_audit = load_area_lookup(
        area_parquet(products_root, area),
        int(rule["priority_limit"]),
        int(rule["attention_limit"]),
    )
    print(
        f"{area}: cells={cell_audit['cells']:,} candidates={len(candidates):,}",
        flush=True,
    )
    total = Counter()
    tile_root = destination / "areas" / area / "tiles" / str(ZOOM)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_and_reclassify, origin, area, tile, lookup, timeout): tile
            for tile in sorted(candidates)
        }
        for number, future in enumerate(as_completed(futures), start=1):
            tile, payload, counts = future.result()
            total.update(counts)
            if payload is not None:
                x, y = tile
                path = tile_root / str(x) / f"{y}.pbf.gz"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            if number % 250 == 0 or number == len(futures):
                print(
                    f"  requests={number:,}/{len(futures):,} "
                    f"tiles={total['tiles_found']:,} buildings={total['buildings']:,}",
                    flush=True,
                )

    if total["tiles_found"] == 0:
        raise RuntimeError(f"No remote tiles found for {area}")
    if total["priority"] + total["attention"] + total["other"] != total["buildings"]:
        raise RuntimeError(f"Invalid action-class accounting for {area}")
    result = {
        "area": area,
        "source": origin,
        "cell_audit": dict(cell_audit),
        "tile_audit": dict(total),
        "priority_limit": int(rule["priority_limit"]),
        "attention_limit": int(rule["attention_limit"]),
    }
    area_manifest = destination / "areas" / area / "migration-audit.json"
    area_manifest.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=sorted(GROUPS), required=True)
    parser.add_argument("--products-root", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=45.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    group = GROUPS[args.group]
    destination = args.output_root / group["project"]
    resolved_root = args.output_root.resolve()
    resolved_destination = destination.resolve()
    if resolved_root not in resolved_destination.parents:
        raise RuntimeError("Staging destination escaped output root")
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"Staging destination is not empty: {destination}")
    write_vercel_config(destination)
    rules = json.loads(args.rules.read_text(encoding="utf-8"))["rules"]
    reports = []
    for area in group["areas"]:
        reports.append(
            process_area(
                area=area,
                origin=group["origin"],
                products_root=args.products_root,
                rules=rules,
                destination=destination,
                workers=max(1, args.workers),
                timeout=args.timeout,
            )
        )
    summary = {
        "group": args.group,
        "project": group["project"],
        "origin": group["origin"],
        "areas": reports,
    }
    (destination / "migration-audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
