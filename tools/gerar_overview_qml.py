from __future__ import annotations

import gzip
import json
import math
import shutil
from pathlib import Path

import numpy as np
from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
POINTS_DIR = PROJECT_DIR / "data_tiles" / "final" / "points" / "12"
OUTPUT_DIR = PROJECT_DIR / "data_tiles" / "final" / "overview_qml"
RULES_PATH = PROJECT_DIR / "data_tiles" / "final" / "ranking_rules_2608.json"
ZOOMS = range(6, 12)
TILE_SIZE = 256
QGIS_RANKING_MIN = 1
QGIS_RANKING_MAX = 104032
FCU_REVIEW_PROB_CUTOFF = 0.70
QGIS_PALETTE = [
    (215, 25, 28), (223, 55, 42), (231, 86, 56), (238, 116, 70), (246, 147, 84),
    (253, 175, 98), (253, 187, 112), (254, 198, 125), (254, 210, 139), (254, 221, 152),
    (254, 233, 165), (255, 245, 179), (254, 255, 191), (248, 252, 189), (241, 249, 187),
    (234, 247, 184), (228, 244, 182), (221, 241, 180), (214, 239, 178), (208, 236, 176),
    (201, 233, 174), (194, 230, 172), (188, 228, 169), (181, 225, 167), (174, 222, 165),
    (168, 219, 164), (163, 215, 165), (158, 212, 166), (153, 208, 167), (147, 204, 168),
    (142, 201, 169), (137, 197, 170), (132, 193, 171), (127, 190, 172), (121, 186, 173),
    (116, 182, 173), (111, 179, 174), (106, 175, 175), (100, 171, 176), (95, 168, 177),
    (90, 164, 178), (85, 160, 179), (80, 157, 180), (74, 153, 181), (69, 149, 182),
    (64, 146, 182), (59, 142, 183), (53, 138, 184), (48, 135, 185), (43, 131, 186),
]


def load_ranking_rules() -> dict:
    if not RULES_PATH.exists():
        return {}
    with RULES_PATH.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("rules", {}) or {}


RANKING_RULES = load_ranking_rules()


def qgis_color(value: object) -> tuple[int, int, int]:
    try:
        rank = float(value)
    except (TypeError, ValueError):
        return 255, 237, 160
    span = max(1.0, QGIS_RANKING_MAX - QGIS_RANKING_MIN)
    t = min(1.0, max(0.0, (rank - QGIS_RANKING_MIN) / span))
    idx = min(len(QGIS_PALETTE) - 1, max(0, int(math.floor(t * len(QGIS_PALETTE)))))
    return QGIS_PALETTE[idx]


def numeric(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def max_model_prob(point: dict) -> float:
    vals = [
        numeric(point.get("pc")),
        numeric(point.get("pm")),
        numeric(point.get("pn")),
        numeric(point.get("ps")),
        numeric(point.get("pi")),
        numeric(point.get("p")),
    ]
    vals = [value for value in vals if value is not None]
    return max(vals) if vals else 0.0


def candidate_class_key(point: dict) -> str:
    target = int(numeric(point.get("t")) or 0)
    if target:
        return "mappedLow" if max_model_prob(point) < FCU_REVIEW_PROB_CUTOFF else "mappedFcu"

    area = str(point.get("a") or "")
    rule = RANKING_RULES.get(area)
    rank = numeric(point.get("r"))
    if not rule or rank is None or rank <= 0:
        return "other"

    priority_limit = numeric(rule.get("priority_limit"))
    attention_limit = numeric(rule.get("attention_limit"))
    if priority_limit is not None and rank <= priority_limit:
        return "priority"
    if attention_limit is not None and rank <= attention_limit:
        return "attention"
    return "other"


def webmercator_tile(lat: float, lng: float, zoom: int) -> tuple[int, int, int, int] | None:
    if not (-85.05112878 <= lat <= 85.05112878 and -180 <= lng <= 180):
        return None
    n = 2 ** zoom
    x_float = (lng + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y_float = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    tile_x = int(min(n - 1, max(0, math.floor(x_float))))
    tile_y = int(min(n - 1, max(0, math.floor(y_float))))
    px = int(min(TILE_SIZE - 1, max(0, math.floor((x_float - tile_x) * TILE_SIZE))))
    py = int(min(TILE_SIZE - 1, max(0, math.floor((y_float - tile_y) * TILE_SIZE))))
    return tile_x, tile_y, px, py


def clear_output() -> None:
    root = PROJECT_DIR.resolve()
    target = OUTPUT_DIR.resolve()
    if root not in target.parents:
        raise RuntimeError(f"Saida fora do projeto: {target}")
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def iter_points():
    files = sorted(POINTS_DIR.rglob("*.json.gz"))
    for file_path in files:
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            payload = json.load(f)
        for point in payload.get("p", []):
            yield point


def marker_radius(zoom: int) -> int:
    if zoom <= 7:
        return 0
    if zoom <= 9:
        return 1
    return 2


def paint_overview_zoom(zoom: int) -> tuple[int, int]:
    tiles: dict[tuple[int, int], np.ndarray] = {}
    radius = marker_radius(zoom)
    count = 0
    skipped_other = 0
    for point in iter_points():
        cls_key = candidate_class_key(point)
        if cls_key == "other":
            skipped_other += 1
            continue
        try:
            lat = float(point["lat"])
            lng = float(point["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        tile = webmercator_tile(lat, lng, zoom)
        if tile is None:
            continue
        tx, ty, px, py = tile
        arr = tiles.setdefault((tx, ty), np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8))
        r, g, b = qgis_color(point.get("rt", point.get("r")))
        x0, x1 = max(0, px - radius), min(TILE_SIZE, px + radius + 1)
        y0, y1 = max(0, py - radius), min(TILE_SIZE, py + radius + 1)
        arr[y0:y1, x0:x1, 0] = r
        arr[y0:y1, x0:x1, 1] = g
        arr[y0:y1, x0:x1, 2] = b
        arr[y0:y1, x0:x1, 3] = 225
        count += 1

    for (tx, ty), arr in tiles.items():
        out_dir = OUTPUT_DIR / str(zoom) / str(tx)
        out_dir.mkdir(parents=True, exist_ok=True)
        Image.fromarray(arr, mode="RGBA").save(out_dir / f"{ty}.png", optimize=True)
    return len(tiles), count, skipped_other


def main() -> None:
    clear_output()
    summary = {}
    for zoom in ZOOMS:
        tile_count, point_count, skipped_other = paint_overview_zoom(zoom)
        summary[str(zoom)] = {
            "tiles": tile_count,
            "points_rendered": point_count,
            "points_skipped_other": skipped_other,
        }
        print(f"zoom {zoom}: {tile_count} tiles, {point_count} pontos renderizados, {skipped_other} demais areas ocultos")
    with (OUTPUT_DIR / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "source": str(POINTS_DIR),
                "field": "ranking_total",
                "classes_rendered": ["priority", "attention", "mappedFcu", "mappedLow"],
                "classes_hidden": ["other"],
                "qml_min": QGIS_RANKING_MIN,
                "qml_max": QGIS_RANKING_MAX,
                "zooms": summary,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


if __name__ == "__main__":
    main()
