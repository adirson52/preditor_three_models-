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
OUTPUT_CLASS_DIR = PROJECT_DIR / "data_tiles" / "final" / "overview_qml_classes"
OUTPUT_ACTION_DIR = PROJECT_DIR / "data_tiles" / "final" / "overview_action"
RULES_PATH = PROJECT_DIR / "data_tiles" / "final" / "ranking_rules_2608.json"
ZOOMS = range(6, 12)
TILE_SIZE = 256
QGIS_RANKING_MIN = 1
QGIS_RANKING_MAX = 104032
QML_ALPHA_HIGH = 225
QML_ALPHA_LOW = 38
ZOOM_OPACITY_FACTORS = {
    6: 0.50,
    7: 0.58,
    8: 0.66,
    9: 0.75,
    10: 0.86,
    11: 1.00,
}
ACTION_COLORS = {
    "priority": (215, 25, 28),
    "attention": (242, 142, 43),
}
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


def qgis_palette_index(value: object) -> int:
    try:
        rank = float(value)
    except (TypeError, ValueError):
        return 10
    span = max(1.0, QGIS_RANKING_MAX - QGIS_RANKING_MIN)
    position = min(1.0, max(0.0, (rank - QGIS_RANKING_MIN) / span))
    return min(len(QGIS_PALETTE) - 1, max(0, int(math.floor(position * len(QGIS_PALETTE)))))


def qgis_color(value: object) -> tuple[int, int, int]:
    return QGIS_PALETTE[qgis_palette_index(value)]


def qgis_alpha(value: object, zoom: int) -> int:
    base_alpha = QML_ALPHA_HIGH if qgis_palette_index(value) < 10 else QML_ALPHA_LOW
    return max(1, min(255, round(base_alpha * ZOOM_OPACITY_FACTORS[zoom])))


def numeric(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def candidate_class_key(point: dict) -> str:
    area = str(point.get("a") or "")
    rule = RANKING_RULES.get(area)
    rank = numeric(point.get("rt"))
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
    for output in (OUTPUT_DIR, OUTPUT_CLASS_DIR, OUTPUT_ACTION_DIR):
        target = output.resolve()
        if root not in target.parents:
            raise RuntimeError(f"Saida fora do projeto: {target}")
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)


def iter_points():
    files = sorted(POINTS_DIR.rglob("*.json.gz"))
    for file_path in files:
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            payload = json.load(f)
        for point in payload.get("p", []):
            yield point


def marker_radius(zoom: int) -> int:
    if zoom <= 9:
        return 0
    return 1


def paint_marker(
    arr: np.ndarray,
    px: int,
    py: int,
    color: tuple[int, int, int],
    alpha: int,
    radius: int,
) -> None:
    """Pinta 1 px de longe e uma cruz de 5 px nos zooms 10-11."""
    r, g, b = color
    if radius == 0:
        arr[py, px, :] = (r, g, b, alpha)
        return

    x0, x1 = max(0, px - radius), min(TILE_SIZE, px + radius + 1)
    y0, y1 = max(0, py - radius), min(TILE_SIZE, py + radius + 1)
    arr[py, x0:x1, 0] = r
    arr[py, x0:x1, 1] = g
    arr[py, x0:x1, 2] = b
    arr[py, x0:x1, 3] = alpha
    arr[y0:y1, px, 0] = r
    arr[y0:y1, px, 1] = g
    arr[y0:y1, px, 2] = b
    arr[y0:y1, px, 3] = alpha


def paint_overview_zoom(zoom: int) -> tuple[int, int, int, dict[str, dict[str, int]]]:
    qml_tiles: dict[tuple[int, int], np.ndarray] = {}
    qml_class_tiles: dict[str, dict[tuple[int, int], np.ndarray]] = {
        "priority": {},
        "attention": {},
        "other": {},
    }
    action_tiles: dict[tuple[int, int], np.ndarray] = {}
    radius = marker_radius(zoom)
    count = 0
    skipped_other = 0
    class_counts = {"priority": 0, "attention": 0, "other": 0}
    for point in iter_points():
        cls_key = candidate_class_key(point)
        try:
            lat = float(point["lat"])
            lng = float(point["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        tile = webmercator_tile(lat, lng, zoom)
        if tile is None:
            continue
        tx, ty, px, py = tile
        class_arr = qml_class_tiles[cls_key].setdefault(
            (tx, ty), np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
        )
        rank_value = point.get("rt", point.get("r"))
        qml_color = qgis_color(rank_value)
        qml_point_alpha = qgis_alpha(rank_value, zoom)
        paint_marker(class_arr, px, py, qml_color, qml_point_alpha, radius)
        class_counts[cls_key] += 1

        if cls_key == "other":
            skipped_other += 1
            continue

        qml_arr = qml_tiles.setdefault((tx, ty), np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8))
        action_arr = action_tiles.setdefault((tx, ty), np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8))
        paint_marker(qml_arr, px, py, qml_color, qml_point_alpha, radius)
        action_alpha = round(QML_ALPHA_HIGH * ZOOM_OPACITY_FACTORS[zoom])
        paint_marker(action_arr, px, py, ACTION_COLORS[cls_key], action_alpha, radius)
        count += 1

    for output, tiles in ((OUTPUT_DIR, qml_tiles), (OUTPUT_ACTION_DIR, action_tiles)):
        for (tx, ty), arr in tiles.items():
            out_dir = output / str(zoom) / str(tx)
            out_dir.mkdir(parents=True, exist_ok=True)
            Image.fromarray(arr, mode="RGBA").save(out_dir / f"{ty}.png", optimize=True)
    class_summary = {}
    for cls_key, tiles in qml_class_tiles.items():
        for (tx, ty), arr in tiles.items():
            out_dir = OUTPUT_CLASS_DIR / cls_key / str(zoom) / str(tx)
            out_dir.mkdir(parents=True, exist_ok=True)
            Image.fromarray(arr, mode="RGBA").save(out_dir / f"{ty}.png", optimize=True)
        class_summary[cls_key] = {"tiles": len(tiles), "points": class_counts[cls_key]}
    return len(qml_tiles), count, skipped_other, class_summary


def main() -> None:
    clear_output()
    summary = {}
    class_summary = {}
    for zoom in ZOOMS:
        tile_count, point_count, skipped_other, zoom_class_summary = paint_overview_zoom(zoom)
        summary[str(zoom)] = {
            "tiles": tile_count,
            "points_rendered": point_count,
            "points_skipped_other": skipped_other,
        }
        class_summary[str(zoom)] = zoom_class_summary
        print(f"zoom {zoom}: {tile_count} tiles, {point_count} pontos renderizados, {skipped_other} demais areas ocultos")
    manifests = {
        OUTPUT_DIR: {
                "mode": "ranking_qml_antigo",
                "source": str(POINTS_DIR),
                "field": "ranking_total",
                "classes_rendered": ["priority", "attention"],
                "classes_hidden": ["other"],
                "qml_min": QGIS_RANKING_MIN,
                "qml_max": QGIS_RANKING_MAX,
                "zooms": summary,
            },
        OUTPUT_ACTION_DIR: {
                "mode": "classe_acao_escada",
                "source": str(POINTS_DIR),
                "field": "ranking_total",
                "classes_rendered": ["priority", "attention"],
                "classes_hidden": ["other"],
                "colors": ACTION_COLORS,
                "zooms": summary,
            },
    }
    for output, manifest in manifests.items():
        with (output / "manifest.json").open("w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    with (OUTPUT_CLASS_DIR / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump({
            "mode": "ranking_qml_por_classe",
            "source": str(POINTS_DIR),
            "field": "ranking_total",
            "classes": ["priority", "attention", "other"],
            "qml_min": QGIS_RANKING_MIN,
            "qml_max": QGIS_RANKING_MAX,
            "palette_size": len(QGIS_PALETTE),
            "rendering": {
                "marker_radius_by_zoom": {str(zoom): marker_radius(zoom) for zoom in ZOOMS},
                "marker_shape": "single_pixel_or_5_pixel_cross",
                "opacity_factor_by_zoom": {str(zoom): ZOOM_OPACITY_FACTORS[zoom] for zoom in ZOOMS},
                "qml_alpha": {"first_10_colors": QML_ALPHA_HIGH, "remaining_40_colors": QML_ALPHA_LOW},
            },
            "zooms": class_summary,
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
