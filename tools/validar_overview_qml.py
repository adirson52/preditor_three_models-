from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
ROOT = PROJECT_DIR / "data_tiles" / "final" / "overview_qml_classes"
UNIFIED_QML_ROOT = PROJECT_DIR / "data_tiles" / "final" / "overview_qml"
ACTION_ROOT = PROJECT_DIR / "data_tiles" / "final" / "overview_action_classes"
CLASSES = ("priority", "attention", "other")
ACTION_COLORS = {
    "priority": (215, 25, 28),
    "attention": (242, 142, 43),
}


def packed_colors(arr: np.ndarray, mask: np.ndarray) -> set[int]:
    rgb = arr[..., :3][mask].astype(np.uint32)
    packed = (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
    return set(np.unique(packed).tolist())


def main() -> None:
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
        if point_count != 3_774_138:
            raise AssertionError(f"Contagem de pontos divergente no zoom {zoom}: {point_count}")
        if len(colors) != 50:
            raise AssertionError(f"Paleta incompleta no zoom {zoom}: {len(colors)} cores")
        if len(alphas) != 2:
            raise AssertionError(f"Faixas de opacidade divergentes no zoom {zoom}: {sorted(alphas)}")

        unified_paths = list((UNIFIED_QML_ROOT / str(zoom)).rglob("*.png"))
        if len(unified_paths) != qml_manifest["zooms"][str(zoom)]["tiles"]:
            raise AssertionError(f"Quantidade divergente de tiles QML unificados no zoom {zoom}")

        action_alpha = round(225 * manifest["rendering"]["opacity_factor_by_zoom"][str(zoom)])
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
