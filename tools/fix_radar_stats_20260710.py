from __future__ import annotations

import gzip
import importlib.util
import json
import math
import os
from pathlib import Path
import unicodedata

import numpy as np
import pandas as pd


ROOT = Path(r"Z:\Banco de dados Preditor Br\03_preditor_grade31_teste0407")
DASH = ROOT / "03_outputs" / "05_dashboard_b"
PUBLISH = ROOT / "03_outputs" / "05_dashboard_b_vercel_publish"
HTML_PATHS = [DASH / "index.html", PUBLISH / "index.html"]
INPUT_PARQUET = ROOT / "01_data_input" / "0407_grade_50m_base_completa_10_areas.parquet"
PRODUCTION_MODELS = ROOT / "03_outputs" / "00_metadata" / "0407_production_models.json"
MAP_SCRIPT = ROOT / "02_scripts" / "07_dashboard_mapas.py"

TARGET_COL = "has_fcu_centroid"
AREA_COLS = [
    "area_rgint_redencao",
    "area_conc_urb_curitiba",
    "area_conc_urb_fortaleza",
    "area_conc_urb_goiania",
    "area_conc_urb_sao_paulo",
    "area_rgint_macapa",
    "area_rgint_belem",
    "area_conc_urb_rio_de_janeiro",
    "area_medias_conc_urb_rj",
    "area_arranjo_pop_rj",
]

RAW_LABEL_OVERRIDES = {
    "b12": "Banda Sentinel-2 B12",
    "cssi2": "Índice espectral CSSI-2",
    "cssi1": "Índice espectral CSSI-1",
    "p90_gba_area_edif": "P90 área edifícios GBA",
    "gba_edif_por_ha": "Edifícios GBA por célula",
    "gba_num_edif": "Edifícios GBA por célula",
}

RAW_VALUE_COLUMN = {
    "gba_edif_por_ha": "gba_num_edif",
}

GBA_OLD_LABELS = {
    "edificios por hectare gba",
    "edificios por ha gba",
}
GBA_NEW_LABEL = "Edifícios GBA por célula"

DISPLAY_ALIASES = {
    "Moradores em casas": [
        "Moradores em casas por célula",
        "População em casas por célula",
    ],
    "Domicílios em casas": [
        "Domicílios tipo casa",
        "Domicílios tipo casa por célula",
        "Domicílios em casas por célula",
    ],
    "Moradores por casa": [
        "Moradores por domicílio tipo casa",
        "Moradores por domicílio em casa",
    ],
    "Moradores por apartamento": [
        "Moradores por domicílio tipo apartamento",
        "Moradores por domicílio em apartamento",
    ],
    "Domicílios tipo apartamento": [
        "Domicílios tipo apartamento por célula",
        "Domicílios em apartamentos",
        "Domicílios em apartamentos por célula",
    ],
    GBA_NEW_LABEL: [
        "Edifícios por hectare (GBA)",
        "Número de edificações (GBA)",
        "gba_edif_por_ha",
        "gba_num_edif",
    ],
    "Banda Sentinel-2 B12": ["b12"],
    "Índice espectral CSSI-2": ["cssi2"],
    "Índice espectral CSSI-1": ["cssi1"],
    "P90 área edifícios GBA": ["p90_gba_area_edif"],
}


def repair_text(value: object) -> str:
    text = str(value or "")
    if "Ã" in text or "Â" in text:
        try:
            return text.encode("latin1").decode("utf-8")
        except Exception:
            return text
    return text


def norm(value: object) -> str:
    text = repair_text(value)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return "".join(ch if ch.isalnum() else " " for ch in text.lower()).strip()


def load_label_map() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("dashboard_mapas", MAP_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    labels: dict[str, str] = {}
    for source in (getattr(module, "FEATURE_LABELS", {}), getattr(module, "SITE_NAME_OVERRIDES", {})):
        for raw, label in source.items():
            labels[str(raw)] = repair_text(label)
    labels.update(RAW_LABEL_OVERRIDES)
    return labels


def load_dashboard_json(html_path: Path) -> tuple[str, dict, str, str]:
    html = html_path.read_text(encoding="utf-8")
    marker = 'id="ebm-data">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    data = json.loads(html[start:end])
    return html, data, html[:start], html[end:]


def collect_features() -> tuple[set[str], dict[str, str], dict[str, str]]:
    models = json.loads(PRODUCTION_MODELS.read_text(encoding="utf-8"))
    raw_features: set[str] = set()
    area_by_col: dict[str, str] = {}
    for item in models["models"]:
        area_by_col[item["area_col"]] = item["area_name"]
        raw_features.update(item.get("features", []))

    labels = load_label_map()
    value_cols = {raw: RAW_VALUE_COLUMN.get(raw, raw) for raw in raw_features}
    value_cols = {raw: col for raw, col in value_cols.items() if col}
    return raw_features, area_by_col, value_cols


def finite_stats(values: pd.Series) -> tuple[float | None, float | None, float | None]:
    numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if numeric.empty:
        return None, None, None
    arr = numeric.to_numpy(dtype=float)
    return float(np.nanmean(arr)), float(np.nanmedian(arr)), float(np.nanquantile(arr, 0.95))


def compute_stats(raw_features: set[str], area_by_col: dict[str, str], value_cols: dict[str, str]) -> dict:
    cols = sorted(set(AREA_COLS + [TARGET_COL] + list(value_cols.values())))
    print(f"[stats] lendo parquet: {len(cols)} colunas")
    frame = pd.read_parquet(INPUT_PARQUET, columns=cols, engine="pyarrow")
    frame[TARGET_COL] = pd.to_numeric(frame[TARGET_COL], errors="coerce").fillna(0).astype(int)

    labels = load_label_map()
    stats: dict[str, dict[str, dict[str, float | list[float]]]] = {}
    for area_col, area_name in area_by_col.items():
        if area_col not in frame.columns:
            continue
        mask_area = pd.to_numeric(frame[area_col], errors="coerce").fillna(0).astype(int).eq(1)
        area_frame = frame.loc[mask_area]
        if area_frame.empty:
            continue
        mask_fcu = area_frame[TARGET_COL].eq(1)
        area_stats = {"means": {}, "means_fcu": {}, "means_non_fcu": {}, "maxes": {}, "anchors": {}}
        for raw in sorted(raw_features):
            value_col = value_cols.get(raw, raw)
            if value_col not in area_frame.columns:
                continue
            mean_all, median_all, p95_all = finite_stats(area_frame[value_col])
            if mean_all is None:
                continue
            mean_fcu, _, _ = finite_stats(area_frame.loc[mask_fcu, value_col])
            mean_non, _, _ = finite_stats(area_frame.loc[~mask_fcu, value_col])

            label = labels.get(raw, raw)
            aliases = {label, raw}
            if raw == "gba_edif_por_ha":
                aliases.update({GBA_NEW_LABEL, "Edifícios por hectare (GBA)"})
            if raw == "gba_num_edif":
                aliases.update({GBA_NEW_LABEL, "Número de edificações (GBA)"})

            anchors = [float(median_all), float(p95_all if p95_all is not None else median_all)]
            for key in aliases:
                area_stats["means"][key] = mean_all
                area_stats["means_fcu"][key] = mean_fcu if mean_fcu is not None else mean_all
                area_stats["means_non_fcu"][key] = mean_non if mean_non is not None else mean_all
                area_stats["maxes"][key] = anchors
                area_stats["anchors"][key] = anchors

        for source, alias_list in DISPLAY_ALIASES.items():
            source_key = next(
                (key for key in area_stats["means"] if norm(key) == norm(source)),
                None,
            )
            if source_key is None:
                continue
            for alias in alias_list:
                for block in ("means", "means_fcu", "means_non_fcu", "maxes", "anchors"):
                    area_stats[block][alias] = area_stats[block][source_key]
        stats[area_col] = area_stats
        print(f"[stats] {area_name}: {len(area_stats['means'])} chaves")
    return stats


def merge_stats_into_html(html_path: Path, stats_by_area_col: dict, raw_features: set[str]) -> None:
    html, data, prefix, suffix = load_dashboard_json(html_path)
    labels = load_label_map()
    for area_name, area_data in data.items():
        area_col = area_data.get("area_col")
        stats = stats_by_area_col.get(area_col)
        if not stats:
            continue
        for block in ("means", "means_fcu", "means_non_fcu", "maxes", "anchors"):
            area_data.setdefault(block, {}).update(stats[block])
        for raw in raw_features:
            label = labels.get(raw, raw)
            if raw in {"gba_edif_por_ha", "gba_num_edif"}:
                label = GBA_NEW_LABEL
            area_data.setdefault("feature_labels", {})[raw] = label
            area_data.setdefault("feature_meta", {}).setdefault(label, {"sigla": raw, "nome_site": label})
    compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html_path.write_text(prefix + compact + suffix, encoding="utf-8")
    print(f"[html] atualizado: {html_path}")


def format_number(value: float) -> str:
    if not math.isfinite(value):
        return "0"
    rounded = round(value)
    if abs(value - rounded) < 1e-8:
        return str(int(rounded))
    return f"{value:.6g}"


def update_gba_tile_rk(tile_root: Path) -> int:
    if not tile_root.exists():
        return 0
    changed_files = 0
    changed_points = 0
    for x_dir in tile_root.iterdir():
        if not x_dir.is_dir():
            continue
        for tile_path in x_dir.glob("*.json.gz"):
            with gzip.open(tile_path, "rt", encoding="utf-8") as fh:
                data = json.load(fh)
            changed = False
            for point in data.get("p", []):
                rk = point.get("rk")
                if not rk or "hectare" not in rk.lower():
                    continue
                parts_out = []
                point_changed = False
                for part in str(rk).split(";"):
                    bits = part.split(",")
                    if len(bits) >= 3 and "hectare" in norm(bits[0]) and "edif" in norm(bits[0]):
                        try:
                            per_ha = float(bits[-1])
                        except Exception:
                            per_ha = 0.0
                        per_cell = per_ha / 4.0
                        bits[0] = GBA_NEW_LABEL
                        bits[-1] = format_number(per_cell)
                        point_changed = True
                    parts_out.append(",".join(bits))
                if point_changed:
                    point["rk"] = ";".join(parts_out)
                    changed = True
                    changed_points += 1
            if changed:
                with gzip.open(tile_path, "wt", encoding="utf-8", compresslevel=6) as fh:
                    json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
                changed_files += 1
    print(f"[tiles] {tile_root}: arquivos={changed_files}, pontos={changed_points}")
    return changed_points


def main() -> None:
    raw_features, area_by_col, value_cols = collect_features()
    print(f"[features] modelos={len(raw_features)} | colunas_valor={len(set(value_cols.values()))}")
    stats = compute_stats(raw_features, area_by_col, value_cols)
    for html_path in HTML_PATHS:
        if html_path.exists():
            merge_stats_into_html(html_path, stats, raw_features)
    for base in (DASH, PUBLISH):
        update_gba_tile_rk(base / "data_tiles" / "final" / "points" / "12")


if __name__ == "__main__":
    main()
