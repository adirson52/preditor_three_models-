from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
ROOT = PROJECT_DIR / "data_tiles" / "final" / "overview_qml_classes"
CLASSES = ("priority", "attention", "other")


def packed_colors(arr: np.ndarray, mask: np.ndarray) -> set[int]:
    rgb = arr[..., :3][mask].astype(np.uint32)
    packed = (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
    return set(np.unique(packed).tolist())


def main() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
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


if __name__ == "__main__":
    main()
