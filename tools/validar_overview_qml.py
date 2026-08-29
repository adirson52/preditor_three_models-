from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image

from gerar_overview_qml import (
    AREA_QML_DIR,
    QGIS_PALETTE,
    QGIS_RANKING_MAX,
    QGIS_RANKING_MIN,
    RANKING_RULES,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
ROOT = PROJECT_DIR / "data_tiles" / "final" / "overview_qml_classes"
UNIFIED_QML_ROOT = PROJECT_DIR / "data_tiles" / "final" / "overview_qml"
ACTION_ROOT = PROJECT_DIR / "data_tiles" / "final" / "overview_action_classes"
QGIS_STYLE_PATH = (
    PROJECT_DIR / "data_tiles" / "final" / "estilos_qgis" / "estilo_revelando2608.qml"
)
CLASSES = ("priority", "attention", "other")
ACTION_COLORS = {
    "priority": (215, 25, 28),
    "attention": (242, 142, 43),
}


def packed_colors(arr: np.ndarray, mask: np.ndarray) -> set[int]:
    rgb = arr[..., :3][mask].astype(np.uint32)
    packed = (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
    return set(np.unique(packed).tolist())


def validate_qgis_source() -> None:
    root = ET.parse(QGIS_STYLE_PATH).getroot()
    renderer = root.find(".//renderer-v2")
    if renderer is None or renderer.attrib.get("attr") != "ranking_total":
        raise AssertionError("O QML canônico não usa ranking_total")

    ranges = renderer.find("ranges")
    symbols = renderer.find("symbols")
    if ranges is None or symbols is None:
        raise AssertionError("Renderer graduado incompleto no QML canônico")
    range_items = ranges.findall("range")
    symbol_items = sorted(symbols.findall("symbol"), key=lambda item: int(item.attrib["name"]))
    if len(range_items) != 50 or len(symbol_items) != 50:
        raise AssertionError("O QML canônico deve ter exatamente 50 classes")

    qml_colors: list[tuple[int, int, int]] = []
    qml_alphas: set[int] = set()
    for symbol in symbol_items:
        color_option = next(
            option
            for option in symbol.findall(".//Option")
            if option.attrib.get("name") == "color"
        )
        rgba = [int(value) for value in color_option.attrib["value"].split(",")[:4]]
        qml_colors.append(tuple(rgba[:3]))
        qml_alphas.add(rgba[3])
    if qml_colors != QGIS_PALETTE or qml_alphas != {255}:
        raise AssertionError("Cores ou opacidade divergentes do estilo QGIS canônico")

    width = (QGIS_RANKING_MAX - QGIS_RANKING_MIN) / 50
    for index, item in enumerate(range_items):
        expected_lower = QGIS_RANKING_MIN + index * width
        expected_upper = QGIS_RANKING_MIN + (index + 1) * width
        if not math.isclose(float(item.attrib["lower"]), expected_lower, abs_tol=1e-8):
            raise AssertionError(f"Limite inferior divergente na classe QML {index}")
        if not math.isclose(float(item.attrib["upper"]), expected_upper, abs_tol=1e-8):
            raise AssertionError(f"Limite superior divergente na classe QML {index}")
    print("QML canônico: ranking_total, 50 classes, 50 cores e alfa 255 — OK")


def validate_area_qml_styles() -> None:
    for area, rule in sorted(RANKING_RULES.items()):
        path = AREA_QML_DIR / f"estilo_revelando2608_{area}.qml"
        root = ET.parse(path).getroot()
        renderer = root.find(".//renderer-v2")
        ranges = renderer.find("ranges").findall("range") if renderer is not None else []
        if renderer is None or renderer.attrib.get("attr") != "ranking_total" or len(ranges) != 50:
            raise AssertionError(f"QML por área inválido: {area}")
        if not math.isclose(float(ranges[0].attrib["lower"]), 1, rel_tol=0, abs_tol=1e-8):
            raise AssertionError(f"Início da rampa divergente em {area}")
        if not math.isclose(
            float(ranges[-1].attrib["upper"]),
            float(rule["total"]),
            rel_tol=0,
            abs_tol=1e-8,
        ):
            raise AssertionError(f"Fim da rampa divergente em {area}")
    print(f"QML por área: {len(RANKING_RULES)} estilos locais — OK")


def main() -> None:
    validate_qgis_source()
    validate_area_qml_styles()
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    qml_manifest = json.loads((UNIFIED_QML_ROOT / "manifest.json").read_text(encoding="utf-8"))
    action_manifest = json.loads((ACTION_ROOT / "manifest.json").read_text(encoding="utf-8"))
    print(json.dumps(manifest["rendering"], ensure_ascii=False))
    for zoom in range(6, 12):
        colors: set[int] = set()
        alphas: set[int] = set()
        occupied = 0
        class_files: dict[str, int] = {}
        for class_key in CLASSES:
            paths = list((ROOT / class_key / str(zoom)).rglob("*.png"))
            class_files[class_key] = len(paths)
            for path in paths:
                arr = np.asarray(Image.open(path).convert("RGBA"))
                mask = arr[..., 3] > 0
                occupied += int(mask.sum())
                if mask.any():
                    colors.update(packed_colors(arr, mask))
                    alphas.update(np.unique(arr[..., 3][mask]).astype(int).tolist())
        point_count = sum(manifest["zooms"][str(zoom)][key]["points"] for key in CLASSES)
        print(
            f"z{zoom}: files={sum(class_files.values())} classes={class_files} "
            f"points={point_count} colors={len(colors)} alphas={sorted(alphas)} pixels={occupied}"
        )
        total_points = 3_774_138
        sample_divisor = manifest["rendering"]["sample_divisor_by_zoom"][str(zoom)]
        if sample_divisor == 1 and point_count != total_points:
            raise AssertionError(f"Contagem de pontos divergente no zoom {zoom}: {point_count}")
        if sample_divisor > 1:
            expected_sample = total_points / sample_divisor
            if not math.isclose(point_count, expected_sample, rel_tol=0.015):
                raise AssertionError(
                    f"Amostra divergente no zoom {zoom}: {point_count} vs aproximadamente {expected_sample:.0f}"
                )
        if len(colors) != 50:
            raise AssertionError(f"Paleta incompleta no zoom {zoom}: {len(colors)} cores")
        expected_qml_alpha = round(
            manifest["rendering"]["qml_alpha"]["all_50_colors"]
            * manifest["rendering"]["opacity_factor_by_zoom"][str(zoom)]
        )
        if alphas != {expected_qml_alpha}:
            raise AssertionError(
                f"Opacidade QML divergente no zoom {zoom}: {sorted(alphas)} != {expected_qml_alpha}"
            )

        unified_paths = list((UNIFIED_QML_ROOT / str(zoom)).rglob("*.png"))
        if len(unified_paths) != qml_manifest["zooms"][str(zoom)]["tiles"]:
            raise AssertionError(f"Quantidade divergente de tiles QML unificados no zoom {zoom}")
        if qml_manifest["zooms"][str(zoom)]["points_rendered"] != point_count:
            raise AssertionError(f"QML unificado diverge da amostra do zoom {zoom}")
        unified_colors: set[int] = set()
        unified_alphas: set[int] = set()
        for path in unified_paths:
            arr = np.asarray(Image.open(path).convert("RGBA"))
            mask = arr[..., 3] > 0
            if mask.any():
                unified_colors.update(packed_colors(arr, mask))
                unified_alphas.update(np.unique(arr[..., 3][mask]).astype(int).tolist())
        if len(unified_colors) != 50 or unified_alphas != {expected_qml_alpha}:
            raise AssertionError(
                f"QML unificado divergente no zoom {zoom}: "
                f"cores={len(unified_colors)}, alfas={sorted(unified_alphas)}"
            )

        action_alpha = round(
            manifest["rendering"]["action_alpha"]
            * manifest["rendering"]["opacity_factor_by_zoom"][str(zoom)]
        )
        for class_key, expected_rgb in ACTION_COLORS.items():
            paths = list((ACTION_ROOT / class_key / str(zoom)).rglob("*.png"))
            expected_tiles = action_manifest["zooms"][str(zoom)][class_key]["tiles"]
            if len(paths) != expected_tiles:
                raise AssertionError(
                    f"Tiles divergentes em {class_key}, zoom {zoom}: {len(paths)} != {expected_tiles}"
                )
            colors: set[int] = set()
            alphas: set[int] = set()
            for path in paths:
                arr = np.asarray(Image.open(path).convert("RGBA"))
                mask = arr[..., 3] > 0
                if mask.any():
                    colors.update(packed_colors(arr, mask))
                    alphas.update(np.unique(arr[..., 3][mask]).astype(int).tolist())
            expected_color = (expected_rgb[0] << 16) | (expected_rgb[1] << 8) | expected_rgb[2]
            if colors != {expected_color} or alphas != {action_alpha}:
                raise AssertionError(
                    f"Estilo divergente em {class_key}, zoom {zoom}: cores={colors}, alfas={alphas}"
                )
        print(
            f"  camadas independentes: QML={len(unified_paths)} tiles; "
            f"prioridade={action_manifest['zooms'][str(zoom)]['priority']['tiles']}; "
            f"atencao={action_manifest['zooms'][str(zoom)]['attention']['tiles']}; demais=transparente"
        )


if __name__ == "__main__":
    main()
