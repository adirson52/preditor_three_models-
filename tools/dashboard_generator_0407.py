# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import re
import shutil
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import shapely
from PIL import Image, ImageDraw


ROOT = Path(r"Z:\Banco de dados Preditor Br\03_preditor_grade31_teste0407")
DASH_DIR = ROOT / "03_outputs" / "05_dashboard_b"
DATA_TILES_DIR = DASH_DIR / "data_tiles"
FINAL_TILE_DIR = DATA_TILES_DIR / "final"
DOWNLOAD_DIR = DASH_DIR / "downloads"
LOG_PATH = ROOT / "03_outputs" / "00_logs" / "12_dashboard_b_usuario_final.log"

MASTER_GEOPARQUET = (
    ROOT
    / "03_outputs"
    / "04_produtos"
    / "consolidado_3_modelos"
    / "0407_predicoes_3_modelos.geoparquet"
)
INPUT_PARQUET = (
    ROOT / "01_data_input" / "0407_grade_50m_base_completa_10_areas.parquet"
)
SOURCE_DASH = ROOT / "03_outputs" / "05_dashboard"
FINAL_GPKG_DIR = (
    ROOT / "03_outputs" / "07_entrega_final" / "0407_final_somente_4_gpkgs"
)
NOMENCLATURE_FILE = ROOT / "01_data_input" / "0407_nomenclatura_variaveis_site.txt"
SOURCE_TEMPLATE_HTML = SOURCE_DASH / "07_dashboard_ebm_avancado_areas_estudo_completo.html"
SOURCE_METRICS_HTML = SOURCE_DASH / "08_dashboard_metricas_modelos_areas_estudo.html"
WINNER_MANIFEST = ROOT / "03_outputs" / "00_metadata" / "0407_modelos_vencedores.json"

POINT_ZOOM = 12
OVERVIEW_ZOOMS = [6, 7, 8, 9, 10, 11]
ID_LOOKUP_PREFIX_LEN = 8
POINT_BATCH_SIZE = 100_000
TOP_N_LOCAL = 7
TOP_CANDIDATES_PER_AREA = 100
FCU_LOW_PROB_THRESHOLD = 0.70

MOJIBAKE_REPLACEMENTS = {
    "\u00c3\u00a1": "\u00e1",
    "\u00c3\u00a0": "\u00e0",
    "\u00c3\u00a2": "\u00e2",
    "\u00c3\u00a3": "\u00e3",
    "\u00c3\u00a9": "\u00e9",
    "\u00c3\u00aa": "\u00ea",
    "\u00c3\u00ad": "\u00ed",
    "\u00c3\u00b3": "\u00f3",
    "\u00c3\u00b4": "\u00f4",
    "\u00c3\u00b5": "\u00f5",
    "\u00c3\u00ba": "\u00fa",
    "\u00c3\u00a7": "\u00e7",
    "\u00c3\u0081": "\u00c1",
    "\u00c3\u0080": "\u00c0",
    "\u00c3\u0082": "\u00c2",
    "\u00c3\u0083": "\u00c3",
    "\u00c3\u0089": "\u00c9",
    "\u00c3\u008a": "\u00ca",
    "\u00c3\u008d": "\u00cd",
    "\u00c3\u0093": "\u00d3",
    "\u00c3\u0094": "\u00d4",
    "\u00c3\u0095": "\u00d5",
    "\u00c3\u009a": "\u00da",
    "\u00c3\u0087": "\u00c7",
    "\u00c2\u00b7": "\u00b7",
    "\u00c2\u00ba": "\u00ba",
    "\u00c2\u00aa": "\u00aa",
}


def fix_mojibake_pt(text: str) -> str:
    for bad, good in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text

AREA_ORDER = [
    ("Curitiba - Conc. Urbana", "area_conc_urb_curitiba"),
    ("Fortaleza - Conc. Urbana", "area_conc_urb_fortaleza"),
    ("GoiÃ¢nia - Conc. Urbana", "area_conc_urb_goiania"),
    ("Rio de Janeiro - Grande Conc. Urbana", "area_conc_urb_rio_de_janeiro"),
    ("Rio de Janeiro - MÃ©dias Conc. Urbanas", "area_medias_conc_urb_rj"),
    ("Rio de Janeiro - Arranjos Populacionais", "area_arranjo_pop_rj"),
    ("SÃ£o Paulo - Conc. Urbana", "area_conc_urb_sao_paulo"),
    ("BelÃ©m - RGInt", "area_rgint_belem"),
    ("MacapÃ¡ - RGInt", "area_rgint_macapa"),
    ("RedenÃ§Ã£o - RGInt", "area_rgint_redencao"),
]

SCENARIO_LABELS = {
    "completo": "Modelo completo",
    "morfologico": "Modelo morfolÃ³gico",
    "nao_morfologico": "Modelo nÃ£o morfolÃ³gico",
}

AREA_ORDER = [
    ("BelÃ©m - RGInt", "area_rgint_belem"),
    ("Curitiba - Conc. Urbana", "area_conc_urb_curitiba"),
    ("Fortaleza - Conc. Urbana", "area_conc_urb_fortaleza"),
    ("GoiÃ¢nia - Conc. Urbana", "area_conc_urb_goiania"),
    ("MacapÃ¡ - RGInt", "area_rgint_macapa"),
    ("RedenÃ§Ã£o - RGInt", "area_rgint_redencao"),
    ("Rio de Janeiro - Arranjos Populacionais", "area_arranjo_pop_rj"),
    ("Rio de Janeiro - Grande Conc. Urbana", "area_conc_urb_rio_de_janeiro"),
    ("Rio de Janeiro - MÃ©dias Conc. Urbanas", "area_medias_conc_urb_rj"),
    ("SÃ£o Paulo - Conc. Urbana", "area_conc_urb_sao_paulo"),
]

SCENARIO_LABELS = {
    "completo": "Modelo completo",
    "morfologico": "Modelo morfolÃ³gico",
    "nao_morfologico": "Modelo nÃ£o morfolÃ³gico",
}


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    text = f"[{stamp}] {message}"
    print(text, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def clean_float(value: Any, default: float | None = None) -> float | None:
    try:
        value = float(value)
    except Exception:
        return default
    if not math.isfinite(value):
        return default
    return value


def safe_int(value: Any, default: int | None = None) -> int | None:
    number = clean_float(value, None)
    if number is None:
        return default
    return int(round(number))


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


def compact_number(value: Any, default: str = "") -> str:
    number = clean_float(value, None)
    if number is None:
        return default
    return f"{number:.6g}"


def lonlat_to_tile_pixel(lons: np.ndarray, lats: np.ndarray, zoom: int):
    lats = np.clip(lats, -85.05112878, 85.05112878)
    n = 2.0**zoom
    xt = (lons + 180.0) / 360.0 * n
    lat_rad = np.radians(lats)
    yt = (
        1.0
        - np.log(np.tan(lat_rad) + 1.0 / np.cos(lat_rad)) / math.pi
    ) / 2.0 * n
    tx = np.floor(xt).astype("int64")
    ty = np.floor(yt).astype("int64")
    tx = np.clip(tx, 0, (1 << zoom) - 1)
    ty = np.clip(ty, 0, (1 << zoom) - 1)
    px = np.clip((xt - tx) * 256.0, 0, 255.999)
    py = np.clip((yt - ty) * 256.0, 0, 255.999)
    return tx, ty, px, py


def clear_dir(path: Path) -> None:
    path = path.resolve()
    base = DASH_DIR.resolve()
    if not path.is_relative_to(base):
        raise RuntimeError(f"Refusing to clear outside dashboard_b: {path}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def load_feature_labels() -> dict[str, str]:
    if not NOMENCLATURE_FILE.exists():
        return {}
    try:
        frame = pd.read_csv(NOMENCLATURE_FILE, sep="\t", encoding="utf-8-sig")
    except UnicodeDecodeError:
        frame = pd.read_csv(NOMENCLATURE_FILE, sep="\t", encoding="latin1")
    labels: dict[str, str] = {}
    for row in frame.to_dict("records"):
        feature = str(row.get("sigla_tabela", "")).strip()
        label = str(row.get("nome_site_daqui_em_diante", "")).strip()
        if feature:
            labels[feature] = label or feature
    return labels


FEATURE_LABELS = load_feature_labels()


def feature_label(feature: Any) -> str:
    feature = safe_text(feature)
    return FEATURE_LABELS.get(feature, feature)


def top_part(row: pd.Series, scenario: str, position: int) -> str:
    feature = row.get(f"top{position}_feat_{scenario}")
    if not safe_text(feature):
        return ""
    score = row.get(f"top{position}_score_{scenario}")
    value = row.get(f"top{position}_val_{scenario}")
    return (
        f"{feature_label(feature)},"
        f"{compact_number(score, '0')},"
        f"{compact_number(value, '0')}"
    )


def build_candidate_rank_max_model(pf: pq.ParquetFile, schema: set[str]) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    """Rank non-FCU cells per area by the maximum probability across the three models."""
    required = [
        "ID",
        "scope",
        "target",
        "prob_fcu_completo",
        "prob_fcu_morfologico",
        "prob_fcu_nao_morfologico",
    ]
    columns = [column for column in required if column in schema]
    if len(columns) < len(required):
        log("[ranking] colunas insuficientes para ranking por probabilidade maxima; usando ranking existente.")
        return {}, {}

    log("[ranking] calculando ranking visual por max(prob_completo, prob_morfologico, prob_nao_morfologico).")
    frame = pf.read(columns=columns).to_pandas()
    frame["scope"] = frame["scope"].astype(str)
    frame["ID"] = frame["ID"].astype(str)
    frame["target_num"] = pd.to_numeric(frame["target"], errors="coerce").fillna(0).astype(int)
    prob_cols = ["prob_fcu_completo", "prob_fcu_morfologico", "prob_fcu_nao_morfologico"]
    for column in prob_cols:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["prob_max_modelos"] = frame[prob_cols].max(axis=1)

    fcu_counts = frame.loc[frame["target_num"].eq(1)].groupby("scope").size().astype(int).to_dict()
    candidates = frame.loc[
        frame["target_num"].eq(0)
        & frame["scope"].notna()
        & frame["ID"].notna()
        & frame["prob_max_modelos"].notna(),
        ["scope", "ID", "prob_max_modelos"],
    ].copy()
    if candidates.empty:
        return fcu_counts, {}

    candidates.sort_values(["scope", "prob_max_modelos", "ID"], ascending=[True, False, True], inplace=True)
    candidates["rank_max_modelos"] = candidates.groupby("scope").cumcount() + 1
    candidates["rank_limit"] = candidates["scope"].map(lambda area: int(fcu_counts.get(area, 0) or 0) * 2)
    candidates = candidates.loc[candidates["rank_max_modelos"].le(candidates["rank_limit"]) & candidates["rank_limit"].gt(0)]
    rank_lookup = {
        (str(row.scope), str(row.ID)): int(row.rank_max_modelos)
        for row in candidates.itertuples(index=False)
    }
    log(
        "[ranking] ranking max-modelos pronto: "
        f"{len(rank_lookup):,} candidatos dentro do limite 2x FCU; "
        f"{sum(fcu_counts.values()):,} celulas FCU de referencia."
    )
    return fcu_counts, rank_lookup


def build_point_tiles(force: bool) -> dict[str, Any]:
    points_root = FINAL_TILE_DIR / "points" / str(POINT_ZOOM)
    manifest_path = FINAL_TILE_DIR / "points_manifest.json"
    if manifest_path.exists() and not force:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    clear_dir(points_root)

    pf = pq.ParquetFile(MASTER_GEOPARQUET)
    schema = set(pf.schema_arrow.names)
    fcu_counts_rank, rank_lookup = build_candidate_rank_max_model(pf, schema)
    columns = [
        "ID",
        "scope",
        "Polo",
        "target",
        "id_rg2017_mun_nome",
        "winner_scenario",
        "prob_fcu_winner",
        "ranking_candidato_winner",
        "ranking_total_winner",
        "quintil_prob_winner",
        "rank_class_winner",
        "classe_candidato_winner",
        "prob_fcu_completo",
        "prob_fcu_morfologico",
        "prob_fcu_nao_morfologico",
        "geometry",
    ]
    for scenario in SCENARIO_LABELS:
        for pos in range(1, TOP_N_LOCAL + 1):
            columns.extend(
                [
                    f"top{pos}_feat_{scenario}",
                    f"top{pos}_score_{scenario}",
                    f"top{pos}_val_{scenario}",
                ]
            )
    columns = [column for column in columns if column in schema]

    tiles: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    total = 0
    min_lon = min_lat = float("inf")
    max_lon = max_lat = float("-inf")
    fcu_counts: dict[str, int] = defaultdict(int, fcu_counts_rank)
    top_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)

    log("[tiles] criando tiles finais a partir de prob_fcu_winner.")
    for batch in pf.iter_batches(batch_size=POINT_BATCH_SIZE, columns=columns):
        frame = batch.to_pandas()
        geoms = shapely.from_wkb(frame["geometry"].to_numpy())
        centroids = shapely.centroid(geoms)
        lons = shapely.get_x(centroids)
        lats = shapely.get_y(centroids)
        valid = np.isfinite(lons) & np.isfinite(lats)
        if not valid.any():
            continue
        tx, ty, px, py = lonlat_to_tile_pixel(lons, lats, POINT_ZOOM)

        for i in np.where(valid)[0]:
            row = frame.iloc[int(i)]
            area_col = safe_text(row.get("scope"))
            target = safe_int(row.get("target"), 0) or 0
            prob = clean_float(row.get("prob_fcu_winner"), 0.0) or 0.0
            prob_by_scenario = {
                "completo": clean_float(row.get("prob_fcu_completo"), 0.0) or 0.0,
                "morfologico": clean_float(row.get("prob_fcu_morfologico"), 0.0) or 0.0,
                "nao_morfologico": clean_float(row.get("prob_fcu_nao_morfologico"), 0.0) or 0.0,
            }
            point_id = safe_text(row.get("ID"))
            rank_candidate = rank_lookup.get((area_col, point_id))
            winner = safe_text(row.get("winner_scenario"))
            local_scenario = max(prob_by_scenario.items(), key=lambda item: item[1])[0]
            rank_parts = []
            for pos in range(1, TOP_N_LOCAL + 1):
                part = top_part(row, local_scenario, pos)
                if part:
                    rank_parts.append(part)

            point = {
                "x": round(float(px[i]), 3),
                "y": round(float(py[i]), 3),
                "lat": round(float(lats[i]), 7),
                "lng": round(float(lons[i]), 7),
                "id": point_id,
                "a": area_col,
                "al": safe_text(row.get("Polo")),
                "p": round(prob, 6),
                "pc": round(prob_by_scenario["completo"], 6),
                "pm": round(prob_by_scenario["morfologico"], 6),
                "pn": round(prob_by_scenario["nao_morfologico"], 6),
                "w": winner,
                "lw": local_scenario,
                "t": target,
                "r": rank_candidate,
                "rt": safe_int(row.get("ranking_total_winner"), None),
                "q": safe_int(row.get("quintil_prob_winner"), None),
                "rc": safe_int(row.get("rank_class_winner"), None),
                "cc": safe_text(row.get("classe_candidato_winner")),
                "mu": safe_text(row.get("id_rg2017_mun_nome")),
            }
            if rank_parts:
                point["rk"] = ";".join(rank_parts)
            tiles[(int(tx[i]), int(ty[i]))].append(point)
            total += 1
            if target and area_col not in fcu_counts_rank:
                fcu_counts[area_col] += 1
            elif rank_candidate is not None and rank_candidate <= TOP_CANDIDATES_PER_AREA:
                top_candidates[area_col].append(point)

        min_lon = min(min_lon, float(np.nanmin(lons[valid])))
        max_lon = max(max_lon, float(np.nanmax(lons[valid])))
        min_lat = min(min_lat, float(np.nanmin(lats[valid])))
        max_lat = max(max_lat, float(np.nanmax(lats[valid])))
        if total and total % 500_000 < POINT_BATCH_SIZE:
            log(f"[tiles] {total:,} pontos processados.")

    for (x, y), points in tiles.items():
        tile_dir = points_root / str(x)
        tile_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"p": points},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        (tile_dir / f"{y}.json.gz").write_bytes(gzip.compress(payload, compresslevel=7))

    for area_col, rows in top_candidates.items():
        rows.sort(key=lambda item: (item.get("r") or 10**12, -item.get("p", 0)))
        top_candidates[area_col] = rows[:TOP_CANDIDATES_PER_AREA]

    manifest = {
        "scenario": "final",
        "source": str(MASTER_GEOPARQUET),
        "source_mtime": MASTER_GEOPARQUET.stat().st_mtime,
        "tile_zoom": POINT_ZOOM,
        "tile_count": len(tiles),
        "point_count": total,
        "format": "json.gz",
        "bounds": [min_lon, min_lat, max_lon, max_lat],
        "topn": TOP_N_LOCAL,
        "fcu_counts": dict(fcu_counts),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (FINAL_TILE_DIR / "top_candidates.json").write_text(
        json.dumps(top_candidates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def build_id_lookup(manifest: dict[str, Any], force: bool) -> dict[str, Any]:
    out_root = FINAL_TILE_DIR / "id_lookup" / str(ID_LOOKUP_PREFIX_LEN)
    manifest_path = FINAL_TILE_DIR / "id_lookup_manifest.json"
    if manifest_path.exists() and not force:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    clear_dir(out_root)
    points_root = FINAL_TILE_DIR / "points" / str(POINT_ZOOM)
    shards: dict[str, list[list[Any]]] = defaultdict(list)
    point_count = 0
    for tile_path in points_root.rglob("*.json.gz"):
        tile_x = int(tile_path.parent.name)
        tile_y = int(tile_path.name.replace(".json.gz", ""))
        with gzip.open(tile_path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
        for point in data.get("p", []):
            point_id = safe_text(point.get("id"))
            if not point_id:
                continue
            prefix = point_id[:ID_LOOKUP_PREFIX_LEN].upper()
            shards[prefix].append(
                [
                    point_id,
                    point.get("a"),
                    tile_x,
                    tile_y,
                    point.get("p"),
                    point.get("r"),
                    point.get("t"),
                    point.get("mu"),
                    point.get("lat"),
                    point.get("lng"),
                ]
            )
            point_count += 1
    for prefix, points in shards.items():
        payload = json.dumps({"p": points}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        (out_root / f"{prefix}.json.gz").write_bytes(gzip.compress(payload, compresslevel=7))
    lookup_manifest = {
        "scenario": "final",
        "prefix_len": ID_LOOKUP_PREFIX_LEN,
        "format": "json.gz",
        "record": ["id", "area", "tile_x", "tile_y", "probability", "rank", "target", "municipio", "lat", "lng"],
        "shard_count": len(shards),
        "point_count": point_count,
        "tile_count": manifest.get("tile_count"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    manifest_path.write_text(json.dumps(lookup_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return lookup_manifest


def point_style(point: dict[str, Any], fcu_counts: dict[str, int]):
    area = safe_text(point.get("a"))
    target = safe_int(point.get("t"), 0) or 0
    rank = safe_int(point.get("r"), None)
    n_fcu = int(fcu_counts.get(area, 0) or 0)
    probs = [
        clean_float(point.get("pc"), None),
        clean_float(point.get("pm"), None),
        clean_float(point.get("pn"), None),
    ]
    valid_probs = [value for value in probs if value is not None and math.isfinite(value)]
    max_prob = max(valid_probs) if valid_probs else (clean_float(point.get("p"), 0.0) or 0.0)
    if target and max_prob < FCU_LOW_PROB_THRESHOLD:
        return (0, 0, 0, 0), 0.0, "mappedLow"
    if target:
        return (0, 0, 0, 0), 0.0, "mappedFcu"
    if rank is not None and rank > 0 and n_fcu > 0 and rank <= math.ceil(n_fcu / 2):
        return (240, 59, 32, 225), 1.85, "priority"
    if rank is not None and rank > 0 and n_fcu > 0 and rank <= n_fcu * 2:
        return (254, 178, 76, 215), 1.65, "attention"
    return (255, 237, 160, 16), 0.65, "other"


def build_overview_tiles(manifest: dict[str, Any], force: bool) -> dict[str, Any]:
    out_root = FINAL_TILE_DIR / "overview"
    manifest_path = FINAL_TILE_DIR / "overview_manifest.json"
    if manifest_path.exists() and not force:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    clear_dir(out_root)
    point_root = FINAL_TILE_DIR / "points" / str(POINT_ZOOM)
    fcu_counts = manifest.get("fcu_counts", {})
    tiles: dict[tuple[int, int, int], tuple[Image.Image, ImageDraw.ImageDraw]] = {}
    class_counts: dict[str, int] = defaultdict(int)
    drawn = 0

    def get_tile(z: int, x: int, y: int):
        key = (z, x, y)
        if key not in tiles:
            image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            tiles[key] = (image, ImageDraw.Draw(image, "RGBA"))
        return tiles[key]

    log("[overview] criando tiles PNG de visÃ£o geral.")
    for tile_path in point_root.rglob("*.json.gz"):
        source_x = int(tile_path.parent.name)
        source_y = int(tile_path.name.replace(".json.gz", ""))
        with gzip.open(tile_path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
        for point in data.get("p", []):
            color, radius, class_key = point_style(point, fcu_counts)
            if color[3] <= 0 or radius <= 0:
                continue
            px12 = source_x + float(point.get("x", 0)) / 256.0
            py12 = source_y + float(point.get("y", 0)) / 256.0
            class_counts[class_key] += 1
            drawn += 1
            for z in OVERVIEW_ZOOMS:
                factor = 2 ** (POINT_ZOOM - z)
                xf = px12 / factor
                yf = py12 / factor
                tx = int(math.floor(xf))
                ty = int(math.floor(yf))
                x = (xf - tx) * 256.0
                y = (yf - ty) * 256.0
                z_radius = radius + (0.22 if z <= 7 and class_key in {"priority", "attention"} else 0)
                _, draw = get_tile(z, tx, ty)
                draw.ellipse((x - z_radius, y - z_radius, x + z_radius, y + z_radius), fill=color)
    for (z, x, y), (image, _) in tiles.items():
        if not image.getbbox():
            continue
        tile_dir = out_root / str(z) / str(x)
        tile_dir.mkdir(parents=True, exist_ok=True)
        image.save(tile_dir / f"{y}.png", optimize=True)
    overview_manifest = {
        "scenario": "final",
        "zooms": OVERVIEW_ZOOMS,
        "tile_count": len(tiles),
        "drawn_points": drawn,
        "class_counts": dict(class_counts),
        "format": "png",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    manifest_path.write_text(json.dumps(overview_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return overview_manifest


def build_fcu_adherence(force: bool) -> Path:
    out_path = DATA_TILES_DIR / "fcu_aderencia.geojson"
    source_path = SOURCE_DASH / "data_tiles" / "fcus_areas_estudo.geojson"
    if out_path.exists() and not force:
        with out_path.open("r", encoding="utf-8", errors="ignore") as handle:
            head = handle.read(200_000)
        if "prob_media_max_modelos" in head:
            return out_path
        log("[fcu] camada antiga detectada; recalculando aderÃªncia com mÃ¡ximo dos 3 modelos.")
    if not source_path.exists():
        out_path.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
        return out_path

    log("[fcu] calculando aderÃªncia das FCUs mapeadas.")
    probs = pq.read_table(
        MASTER_GEOPARQUET,
        columns=[
            "ID",
            "prob_fcu_winner",
            "prob_fcu_completo",
            "prob_fcu_morfologico",
            "prob_fcu_nao_morfologico",
            "target",
        ],
    ).to_pandas()
    prob_cols = ["prob_fcu_completo", "prob_fcu_morfologico", "prob_fcu_nao_morfologico"]
    for column in ["prob_fcu_winner", *prob_cols]:
        probs[column] = pd.to_numeric(probs[column], errors="coerce")
    probs["prob_fcu_max_modelos"] = probs[prob_cols].max(axis=1)
    ids = pq.read_table(
        INPUT_PARQUET,
        columns=["id", "id_fcu", "cd_fcu", "nm_fcu"],
    ).to_pandas()
    ids = ids.rename(columns={"id": "ID"})
    frame = probs.merge(ids, on="ID", how="left")
    frame = frame[
        frame["target"].eq(1)
        & frame["id_fcu"].notna()
        & frame["id_fcu"].astype(str).ne("")
    ].copy()
    if frame.empty:
        shutil.copy2(source_path, out_path)
        return out_path
    stats = (
        frame.groupby("id_fcu", dropna=True)
        .agg(
            prob_media_winner=("prob_fcu_winner", "mean"),
            prob_mediana_winner=("prob_fcu_winner", "median"),
            prob_min_winner=("prob_fcu_winner", "min"),
            prob_max_winner=("prob_fcu_winner", "max"),
            prob_media_max_modelos=("prob_fcu_max_modelos", "mean"),
            prob_mediana_max_modelos=("prob_fcu_max_modelos", "median"),
            prob_min_max_modelos=("prob_fcu_max_modelos", "min"),
            prob_max_max_modelos=("prob_fcu_max_modelos", "max"),
            n_celulas=("prob_fcu_winner", "size"),
        )
        .reset_index()
    )
    stats["id_fcu"] = stats["id_fcu"].astype(str)
    stats["aderencia_modelo"] = np.where(
        stats["prob_media_max_modelos"].ge(FCU_LOW_PROB_THRESHOLD),
        "fcu_mantida",
        "fcu_revisao",
    )

    gdf = gpd.read_file(source_path)
    if "id_fcu" in gdf.columns:
        gdf["id_fcu"] = gdf["id_fcu"].astype(str)
        gdf = gdf.merge(stats, on="id_fcu", how="left")
    else:
        gdf["prob_media_winner"] = np.nan
        gdf["prob_media_max_modelos"] = np.nan
        gdf["aderencia_modelo"] = "sem_dado"
    gdf["aderencia_modelo"] = gdf["aderencia_modelo"].fillna("sem_dado")
    gdf["prob_media_winner"] = pd.to_numeric(gdf["prob_media_winner"], errors="coerce")
    gdf["prob_media_max_modelos"] = pd.to_numeric(gdf["prob_media_max_modelos"], errors="coerce")
    gdf = gdf.to_crs(4674)
    gdf["geometry"] = gdf.geometry.simplify(0.00002, preserve_topology=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GeoJSON")
    return out_path


def hardlink_or_copy(source: Path, dest: Path, force: bool) -> str:
    if not source.exists():
        raise FileNotFoundError(source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if not force and dest.stat().st_size == source.stat().st_size:
            return "existing"
        dest.unlink()
    try:
        os.link(source, dest)
        return "hardlink"
    except OSError:
        shutil.copy2(source, dest)
        return "copy"


def prepare_downloads(force: bool) -> list[dict[str, Any]]:
    files = [
        (
            MASTER_GEOPARQUET,
            DOWNLOAD_DIR / "0407_predicoes_3_modelos.geoparquet",
            "GeoParquet final consolidado",
        ),
        (
            FINAL_GPKG_DIR / "0407_base_inicial_completa_10_areas.gpkg",
            DOWNLOAD_DIR / "0407_base_inicial_completa_10_areas.gpkg",
            "GPKG base inicial",
        ),
        (
            FINAL_GPKG_DIR / "0407_modelo_completo.gpkg",
            DOWNLOAD_DIR / "0407_modelo_completo.gpkg",
            "GPKG modelo completo",
        ),
        (
            FINAL_GPKG_DIR / "0407_modelo_morfologico.gpkg",
            DOWNLOAD_DIR / "0407_modelo_morfologico.gpkg",
            "GPKG modelo morfolÃ³gico",
        ),
        (
            FINAL_GPKG_DIR / "0407_modelo_nao_morfologico.gpkg",
            DOWNLOAD_DIR / "0407_modelo_nao_morfologico.gpkg",
            "GPKG modelo nÃ£o morfolÃ³gico",
        ),
    ]
    out = []
    for source, dest, label in files:
        mode = hardlink_or_copy(source, dest, force=force)
        root_dest = DASH_DIR / dest.name
        root_mode = hardlink_or_copy(source, root_dest, force=force)
        out.append(
            {
                "label": label,
                "file": dest.name,
                "root_file": root_dest.name,
                "size_mb": round(dest.stat().st_size / 1024 / 1024, 1),
                "mode": mode,
                "root_mode": root_mode,
            }
        )
    (DOWNLOAD_DIR / "manifest_downloads.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if SOURCE_METRICS_HTML.exists():
        metrics_html = SOURCE_METRICS_HTML.read_text(encoding="utf-8")
        (DASH_DIR / "analise_modelos.html").write_text(
            patch_metrics_dashboard_html(metrics_html),
            encoding="utf-8",
        )
    return out


def write_static_metadata(manifest: dict[str, Any], downloads: list[dict[str, Any]]) -> None:
    DATA_TILES_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_TILES_DIR / "manifest.json").write_text(
        json.dumps(
            {
                "final": manifest,
                "fcu_adherence": "fcu_aderencia.geojson",
                "downloads": downloads,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (DASH_DIR / "vercel.json").write_text(
        json.dumps(
            {
                "headers": [
                    {
                        "source": "/data_tiles/(.*).json.gz",
                        "headers": [
                            {"key": "Content-Type", "value": "application/json; charset=utf-8"},
                            {"key": "Content-Encoding", "value": "gzip"},
                            {"key": "Cache-Control", "value": "public, max-age=31536000, immutable"},
                        ],
                    },
                    {
                        "source": "/data_tiles/(.*).png",
                        "headers": [
                            {"key": "Cache-Control", "value": "public, max-age=31536000, immutable"},
                        ],
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (DASH_DIR / ".vercelignore").write_text(
        "downloads/\n*.gpkg\n*.geoparquet\n*.zip\n__pycache__/\n",
        encoding="utf-8",
    )
    (DASH_DIR / ".gitignore").write_text(
        ".vercel/\n__pycache__/\n",
        encoding="utf-8",
    )
    (DASH_DIR / "README.md").write_text(
        "# Dashboard B - Preditor FCU\n\n"
        "Dashboard final para usuario publico. A pasta downloads contem "
        "hardlinks locais para os GPKGs e GeoParquet completos; ela e "
        "excluida do deploy Vercel por .vercelignore.\n",
        encoding="utf-8",
    )


def build_winner_payload() -> dict[str, Any]:
    payloads: dict[str, dict[str, Any]] = {}
    payload_by_area_col: dict[str, dict[str, Any]] = {}
    key_by_area_col: dict[str, str] = {}
    for scenario in SCENARIO_LABELS:
        path = SOURCE_DASH / f"07_dashboard_ebm_payload_areas_estudo_{scenario}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        payloads[scenario] = data
        payload_by_area_col[scenario] = {}
        for area_name, payload in data.items():
            area_col = safe_text(payload.get("area_col"))
            if area_col:
                payload_by_area_col[scenario][area_col] = payload
                key_by_area_col.setdefault(area_col, area_name)

    winners_raw = json.loads(WINNER_MANIFEST.read_text(encoding="utf-8"))
    winners = {
        safe_text(row.get("area_col")): row
        for row in winners_raw.get("winners", [])
        if safe_text(row.get("area_col"))
    }

    combined: dict[str, Any] = {}
    for preferred_area_name, area_col in AREA_ORDER:
        winner = winners.get(area_col)
        if not winner:
            continue
        scenario = safe_text(winner.get("scenario")) or "completo"
        source_payload = payload_by_area_col.get(scenario, {}).get(area_col)
        if source_payload is None:
            source_payload = payload_by_area_col.get("completo", {}).get(area_col)
            scenario = "completo"
        if source_payload is None:
            continue
        item = json.loads(json.dumps(source_payload, ensure_ascii=False))
        item["scenario"] = "Resultado final"
        item["winner_scenario_key"] = scenario
        item["winner_scenario_label"] = safe_text(
            winner.get("scenario_label")
        ) or SCENARIO_LABELS.get(scenario, scenario)
        item["winner_average_precision"] = winner.get("average_precision")
        item["winner_n_features"] = winner.get("n_features")
        area_name = preferred_area_name or key_by_area_col.get(area_col) or safe_text(winner.get("area_name")) or area_col
        combined[area_name] = item
    return combined


def build_model_intercepts() -> dict[str, dict[str, float]]:
    intercepts: dict[str, dict[str, float]] = defaultdict(dict)
    for scenario in SCENARIO_LABELS:
        path = SOURCE_DASH / f"07_dashboard_ebm_payload_areas_estudo_{scenario}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for payload in data.values():
            area_col = safe_text(payload.get("area_col"))
            intercept = clean_float(payload.get("intercept"), None)
            if area_col and intercept is not None:
                intercepts[area_col][scenario] = float(intercept)
    return {area: dict(values) for area, values in intercepts.items()}


FINAL_THEME_CSS = r"""
<style id="cefavela-final-theme">
  :root {
    --primary: #0b3d5c;
    --accent: #0b7fa3;
    --cyan: #19a7bd;
    --bg: #f4f8fa;
    --border: #d8e8ee;
    --muted: #567281;
  }
  body { background: var(--bg); }
  .site-header, .card, .panel, .metric-card {
    border-color: var(--border) !important;
  }
  .site-nav-links a.active,
  .site-nav a.active,
  .tab-btn.active,
  button.primary {
    background: #0b3d5c !important;
    border-color: #0b3d5c !important;
    color: #fff !important;
  }
  .site-nav-links a:hover,
  .site-nav a:hover,
  button:hover {
    border-color: #0b7fa3 !important;
  }
  .tab-nav {
    display: none !important;
  }
  #polo-title, h1, h2 {
    color: #0b3d5c;
  }
  .chip.risk-high {
    border-left-color: #0b7fa3 !important;
  }
  .all-points-control {
    border-color: #d8e8ee !important;
    box-shadow: 0 2px 7px rgba(11, 61, 92, .18) !important;
  }
</style>
"""


FINAL_NAV_HTML = (
    '<nav class="site-nav-links" aria-label="Navegacao principal">'
    '<a class="active" href="index.html">InÃ­cio</a>'
    '<a href="https://cefavela.ufabc.edu.br/revelando-favelas-arcabouco-metodologico-para-identificacao-e-caracterizacao-de-favelas/" target="_blank" rel="noopener noreferrer">Saiba mais</a>'
    '</nav>'
)


def patch_metrics_dashboard_html(html: str) -> str:
    html = re.sub(
        r'<nav class="site-nav-links"[^>]*>.*?</nav>',
        FINAL_NAV_HTML,
        html,
        count=1,
        flags=re.S,
    )
    if "cefavela-final-theme" not in html:
        html = html.replace("</head>", FINAL_THEME_CSS + "\n</head>", 1)
    return html


def inject_final_dashboard_patches(html: str, payload: dict[str, Any]) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    intercepts_json = json.dumps(build_model_intercepts(), ensure_ascii=False, separators=(",", ":"))
    html = re.sub(
        r'(<script type="application/json" id="ebm-data">).*?(</script>)',
        lambda match: match.group(1) + payload_json + match.group(2),
        html,
        count=1,
        flags=re.S,
    )
    html = html.replace(
        "        let App = {",
        f"        const FINAL_MODEL_INTERCEPTS = {intercepts_json};\n        let App = {{",
        1,
    )
    html = re.sub(
        r"<title>.*?</title>",
        "<title>Preditor FCU - Resultado Final</title>",
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(
        r'<nav class="site-nav-links"[^>]*>.*?</nav>',
        FINAL_NAV_HTML,
        html,
        count=1,
        flags=re.S,
    )
    if "cefavela-final-theme" not in html:
        html = html.replace("</head>", FINAL_THEME_CSS + "\n</head>", 1)
    html = html.replace('const SCENARIO_KEY = "completo";', 'const SCENARIO_KEY = "final";')
    html = re.sub(
        r"const FCU_URL = 'data_tiles/fcus_areas_estudo\.geojson\?v=base0407_fcu_original';",
        "const FCU_URL = 'data_tiles/fcu_aderencia.geojson?v=base0407_final_fcu_v2';",
        html,
        count=1,
    )
    fcu_canvas_code = r"""
  function finalCanvasAreaCol() {
    if (typeof App === 'undefined') return null;
    return (App.currentPolo && App.currentPolo.area_col) ||
      (App.selectedSample && App.selectedSample.scope) ||
      (App.currentPoloName && App.data && App.data[App.currentPoloName] ? App.data[App.currentPoloName].area_col : null);
  }

  function finalFcuCanvasStyle(feature, phase) {
    const key = fcuFeatureClass(feature);
    if (phase === 'base') {
      if (!finalClassVisible(key)) return null;
      return {stroke: 'rgba(2,6,23,0.90)', fill: 'rgba(17,24,39,0.24)', width: 2.2};
    }
    if (!finalClassVisible(key)) return null;
    if (key === 'mappedLow') return {stroke: 'rgba(75,85,99,1)', fill: 'rgba(189,189,189,0.72)', width: 2.4};
    return {stroke: 'rgba(31,41,55,1)', fill: 'rgba(75,85,99,0.66)', width: 2.8};
  }

  function finalProjectRing(ring, coords) {
    const pts = [];
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const coord of ring || []) {
      const lng = Number(coord[0]);
      const lat = Number(coord[1]);
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
      const p = App.map.project(L.latLng(lat, lng), coords.z);
      const x = p.x - coords.x * 256;
      const y = p.y - coords.y * 256;
      pts.push([x, y]);
      minX = Math.min(minX, x); minY = Math.min(minY, y);
      maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
    }
    return {pts, minX, minY, maxX, maxY};
  }

  function finalDrawFcuFeature(ctx, feature, coords, style) {
    if (!style || !feature || !feature.geometry) return;
    const geom = feature.geometry;
    const polygons = geom.type === 'Polygon' ? [geom.coordinates] : (geom.type === 'MultiPolygon' ? geom.coordinates : []);
    for (const rings of polygons) {
      const projected = (rings || []).map(ring => finalProjectRing(ring, coords)).filter(r => r.pts.length >= 3);
      if (!projected.length) continue;
      const minX = Math.min(...projected.map(r => r.minX));
      const minY = Math.min(...projected.map(r => r.minY));
      const maxX = Math.max(...projected.map(r => r.maxX));
      const maxY = Math.max(...projected.map(r => r.maxY));
      const pad = Math.max(4, Number(style.width || 1) + 2);
      if (maxX < -pad || maxY < -pad || minX > 256 + pad || minY > 256 + pad) continue;
      ctx.beginPath();
      for (const ring of projected) {
        ring.pts.forEach((pt, i) => {
          if (i === 0) ctx.moveTo(pt[0], pt[1]);
          else ctx.lineTo(pt[0], pt[1]);
        });
        ctx.closePath();
      }
      ctx.fillStyle = style.fill;
      ctx.strokeStyle = style.stroke;
      ctx.lineWidth = style.width;
      ctx.fill('evenodd');
      ctx.stroke();
    }
  }

  const FinalFcuCanvasLayer = L.GridLayer.extend({
    createTile: function(coords, done) {
      const tile = L.DomUtil.create('canvas', 'leaflet-tile');
      tile.width = tile.height = 256;
      const ctx = tile.getContext('2d');
      if (!fcuDataPromise) {
        fcuDataPromise = fetch(FCU_URL).then(r => r.ok ? r.json() : {type:'FeatureCollection', features:[]});
      }
      fcuDataPromise.then(data => {
        const areaCol = finalCanvasAreaCol();
        const features = (data.features || []).filter(f => !areaCol || (f.properties && f.properties.area_col === areaCol));
        for (const feature of features) finalDrawFcuFeature(ctx, feature, coords, finalFcuCanvasStyle(feature, 'base'));
        for (const feature of features) finalDrawFcuFeature(ctx, feature, coords, finalFcuCanvasStyle(feature, 'status'));
        done(null, tile);
      }).catch(() => done(null, tile));
      return tile;
    }
  });
"""
    html = html.replace("  let fcuDataPromise = null;\n", "  let fcuDataPromise = null;\n" + fcu_canvas_code)
    html = html.replace("base0407_points_v1", "base0407_points_v2")
    html = html.replace("base0407_overview_v1", "base0407_overview_v10")
    html = html.replace("base0407_overview_v2", "base0407_overview_v10")
    html = html.replace("base0407_overview_v9", "base0407_overview_v10")
    html = html.replace(
        "fetch(`${LOOKUP_BASE}/${encodeURIComponent(key)}.json.gz`)",
        "fetch(`${LOOKUP_BASE}/${encodeURIComponent(key)}.json.gz?v=base0407_lookup_v3`)",
    )
    scenario_i18n = {
        "pt": {
            "label": "Resultado final",
            "subtitle": (
                "Probabilidade final do modelo vencedor em cada Ã¡rea de estudo. "
                "Ao clicar na cÃ©lula, o painel mostra o cenÃ¡rio vencedor e as trÃªs probabilidades."
            ),
        },
        "en": {
            "label": "Final result",
            "subtitle": (
                "Final probability from the winning model in each study area. "
                "Click a cell to see the winning scenario and the three model probabilities."
            ),
        },
    }
    scenario_i18n = {
        "pt": {
            "label": "Resultado final",
            "subtitle": (
                "Probabilidade final do modelo vencedor em cada Ã¡rea de estudo. "
                "Ao clicar na cÃ©lula, o painel mostra o cenÃ¡rio vencedor e as trÃªs probabilidades."
            ),
        },
        "en": {
            "label": "Final result",
            "subtitle": (
                "Final probability from the winning model in each study area. "
                "Click a cell to see the winning scenario and the three model probabilities."
            ),
        },
    }
    html = re.sub(
        r"const SCENARIO_I18N = .*?;\n",
        "  const SCENARIO_I18N = "
        + json.dumps(scenario_i18n, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        html,
        count=1,
    )
    html = html.replace("global_importance.slice(0, 6)", "global_importance.slice(0, 7)")
    html = html.replace(".slice(0, 5);\n            const top5Local", ".slice(0, 7);\n            const top5Local")
    html = html.replace(
        "            const top5Local = localContribs.map(c => c[0]);",
        "            const top5Local = localContribs.map(c => c[0]);\n"
        "            window.__RF_LAST_RADAR_FEATURES__ = top5Local.slice();",
    )
    radar_resolver_js = r"""

            const radarAliases = {
                'Moradores em casas por célula': ['Moradores em casas', 'ibge_mediapopc'],
                'Moradores em casas': ['Moradores em casas por célula', 'ibge_mediapopc'],
                'Domicílios tipo casa': ['Domicílios em casas', 'Domicílios em casas por célula', 'ibge_mediadomc'],
                'Domicílios em casas por célula': ['Domicílios tipo casa', 'Domicílios em casas', 'ibge_mediadomc'],
                'Domicílios em casas': ['Domicílios tipo casa', 'Domicílios em casas por célula', 'ibge_mediadomc'],
                'Moradores por domicílio tipo casa': ['Moradores por casa', 'ibge_mediapopdomc'],
                'Moradores por casa': ['Moradores por domicílio tipo casa', 'ibge_mediapopdomc'],
                'Moradores em apartamentos por célula': ['Moradores por apartamento', 'ibge_mediapopa'],
                'Moradores por apartamento': ['Moradores em apartamentos por célula', 'ibge_mediapopdoma'],
                'Domicílios tipo apartamento': ['Domicílios tipo apartamento por célula', 'Domicílios em apartamentos', 'ibge_mediadoma'],
                'Domicílios tipo apartamento por célula': ['Domicílios tipo apartamento', 'Domicílios em apartamentos', 'ibge_mediadoma'],
                'Domicílios em apartamentos': ['Domicílios tipo apartamento', 'Domicílios tipo apartamento por célula', 'ibge_mediadoma']
            };
            const normRadarKey = value => String(value || '')
                .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
                .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
            const radarCandidateKeys = (feat) => {
                const label = getLabel(feat);
                const out = [feat, label];
                [feat, label].forEach(k => (radarAliases[k] || []).forEach(alias => out.push(alias)));
                const meta = (App.currentPolo && App.currentPolo.feature_meta) ? App.currentPolo.feature_meta : {};
                [feat, label, ...(radarAliases[feat] || []), ...(radarAliases[label] || [])].forEach(k => {
                    if (meta[k] && meta[k].sigla) out.push(meta[k].sigla);
                });
                if (App.currentPolo && App.currentPolo.feature_labels) {
                    Object.entries(App.currentPolo.feature_labels).forEach(([raw, lbl]) => {
                        const keys = [feat, label, ...(radarAliases[feat] || []), ...(radarAliases[label] || [])];
                        if (keys.includes(raw) || keys.includes(lbl)) out.push(raw, lbl);
                    });
                }
                return [...new Set(out.filter(Boolean))];
            };
            const radarResolveKey = (obj, feat) => {
                if (!obj) return null;
                for (const key of radarCandidateKeys(feat)) {
                    if (Object.prototype.hasOwnProperty.call(obj, key)) return key;
                }
                return Object.keys(obj).find(k => radarCandidateKeys(feat).some(c => normRadarKey(c) === normRadarKey(k))) || null;
            };
            const radarLookup = (obj, feat, fallback = null) => {
                const key = radarResolveKey(obj, feat);
                return key ? obj[key] : fallback;
            };
            const radarValue = (obj, feat, fallback = 0) => {
                const value = Number(radarLookup(obj, feat, fallback));
                return Number.isFinite(value) ? value : fallback;
            };
"""
    html = html.replace(
        "            const top5Local = localContribs.map(c => c[0]);\n\n            const rSampleVals",
        "            const top5Local = localContribs.map(c => c[0]);" + radar_resolver_js + "\n            const rSampleVals",
    )
    html = html.replace(
        "            const rSampleVals = top5Local.map(f => sample.values[f] || 0);",
        "            const rSampleVals = top5Local.map(f => radarValue(sample.values, f, 0));",
    )
    html = html.replace(
        "            const rMeanPolo = top5Local.map(f => (mPolo ? mPolo[f] : 0) || 0);",
        "            const rMeanPolo = top5Local.map(f => radarValue(mPolo, f, 0));",
    )
    html = html.replace(
        "            const rMeanFcu = top5Local.map(f => (mFcu ? mFcu[f] : 0) || 0);",
        "            const rMeanFcu = top5Local.map(f => radarValue(mFcu, f, 0));",
    )
    html = html.replace(
        "            const rMeanNonFcu = top5Local.map(f => (mNonFcu ? mNonFcu[f] : 0) || 0);",
        "            const rMeanNonFcu = top5Local.map(f => radarValue(mNonFcu, f, 0));",
    )
    html = html.replace(
        """            const rSampleVals = top5Local.map(f => sample.values[f] || 0);
            const cleanLabels = top5Local.map(f => (window.rfRepairText ? window.rfRepairText(getLabel(f)) : getLabel(f)));

            // --- CÃ¡lculos das MÃ©dias ---
            const mPolo = App.currentPolo.means;
            const mFcu = App.currentPolo.means_fcu;
            const mNonFcu = App.currentPolo.means_non_fcu;
            const mMaxes = App.currentPolo.maxes || {};

            const rMeanPolo = top5Local.map(f => (mPolo ? mPolo[f] : 0) || 0);
            const rMeanFcu = top5Local.map(f => (mFcu ? mFcu[f] : 0) || 0);
            const rMeanNonFcu = top5Local.map(f => (mNonFcu ? mNonFcu[f] : 0) || 0);""",
        """            const radarAliases = {
                'Moradores em casas por célula': ['Moradores em casas', 'ibge_mediapopc'],
                'Moradores em casas': ['Moradores em casas por célula', 'ibge_mediapopc'],
                'Domicílios tipo casa': ['Domicílios em casas', 'Domicílios em casas por célula', 'ibge_mediadomc'],
                'Domicílios em casas por célula': ['Domicílios tipo casa', 'Domicílios em casas', 'ibge_mediadomc'],
                'Domicílios em casas': ['Domicílios tipo casa', 'Domicílios em casas por célula', 'ibge_mediadomc'],
                'Moradores por domicílio tipo casa': ['Moradores por casa', 'ibge_mediapopdomc'],
                'Moradores por casa': ['Moradores por domicílio tipo casa', 'ibge_mediapopdomc'],
                'Moradores em apartamentos por célula': ['Moradores por apartamento', 'ibge_mediapopa'],
                'Moradores por apartamento': ['Moradores em apartamentos por célula', 'ibge_mediapopdoma'],
                'Domicílios tipo apartamento': ['Domicílios tipo apartamento por célula', 'Domicílios em apartamentos', 'ibge_mediadoma'],
                'Domicílios tipo apartamento por célula': ['Domicílios tipo apartamento', 'Domicílios em apartamentos', 'ibge_mediadoma'],
                'Domicílios em apartamentos': ['Domicílios tipo apartamento', 'Domicílios tipo apartamento por célula', 'ibge_mediadoma']
            };
            const normRadarKey = value => String(value || '')
                .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
            const radarCandidateKeys = (feat) => {
                const label = getLabel(feat);
                const out = [feat, label];
                [feat, label].forEach(k => {
                    (radarAliases[k] || []).forEach(alias => out.push(alias));
                });
                const meta = (App.currentPolo && App.currentPolo.feature_meta) ? App.currentPolo.feature_meta : {};
                [feat, label, ...(radarAliases[feat] || []), ...(radarAliases[label] || [])].forEach(k => {
                    if (meta[k] && meta[k].sigla) out.push(meta[k].sigla);
                });
                if (App.currentPolo && App.currentPolo.feature_labels) {
                    Object.entries(App.currentPolo.feature_labels).forEach(([raw, lbl]) => {
                        const keys = [feat, label, ...(radarAliases[feat] || []), ...(radarAliases[label] || [])];
                        if (keys.includes(raw) || keys.includes(lbl)) out.push(raw, lbl);
                    });
                }
                return [...new Set(out.filter(Boolean))];
            };
            const radarResolveKey = (obj, feat) => {
                if (!obj) return null;
                for (const key of radarCandidateKeys(feat)) {
                    if (Object.prototype.hasOwnProperty.call(obj, key)) return key;
                }
                const byNorm = Object.keys(obj).find(k => radarCandidateKeys(feat).some(c => normRadarKey(c) === normRadarKey(k)));
                return byNorm || null;
            };
            const radarLookup = (obj, feat, fallback = null) => {
                const key = radarResolveKey(obj, feat);
                return key ? obj[key] : fallback;
            };
            const radarValue = (obj, feat, fallback = 0) => {
                const value = Number(radarLookup(obj, feat, fallback));
                return Number.isFinite(value) ? value : fallback;
            };
            const cleanLabels = top5Local.map(f => (window.rfRepairText ? window.rfRepairText(getLabel(f)) : getLabel(f)));

            // --- Cálculos das Médias ---
            const mPolo = App.currentPolo.means;
            const mFcu = App.currentPolo.means_fcu;
            const mNonFcu = App.currentPolo.means_non_fcu;
            const mMaxes = App.currentPolo.maxes || {};

            const rSampleVals = top5Local.map(f => radarValue(sample.values, f, 0));
            const rMeanPolo = top5Local.map(f => radarValue(mPolo, f, 0));
            const rMeanFcu = top5Local.map(f => radarValue(mFcu, f, 0));
            const rMeanNonFcu = top5Local.map(f => radarValue(mNonFcu, f, 0));""",
    )
    html = html.replace(
        "                    let anch = mMaxes[feat] || mMaxes[cleanFeat];",
        "                    let anch = radarLookup(mMaxes, feat, null) || mMaxes[cleanFeat];",
    )
    html = html.replace(
        "                const anch = mMaxes[feat] || mMaxes[String(feat || '').replace(/^p_ibge_|^m_ibge_|^s_cad_|^shape_|^decliv_|^m_cad_/g, '')];",
        "                const anch = radarLookup(mMaxes, feat, null) || mMaxes[String(feat || '').replace(/^p_ibge_|^m_ibge_|^s_cad_|^shape_|^decliv_|^m_cad_/g, '')];",
    )
    html = html.replace(
        """            const radarDisplayLabel = (label) => {
                return label;
            };""",
        """            const radarDisplayLabel = (label) => {
                const text = String(label || '');
                if (text.length <= 18) return text;
                const words = text.split(/\\s+/);
                const lines = [];
                let line = '';
                words.forEach(word => {
                    const next = line ? `${line} ${word}` : word;
                    if (next.length > 18 && line) {
                        lines.push(line);
                        line = word;
                    } else {
                        line = next;
                    }
                });
                if (line) lines.push(line);
                return lines.slice(0, 3).join('<br>');
            };""",
    )
    html = html.replace(
        """                polar: {
                    radialaxis:""",
        """                polar: {
                    angularaxis: {
                        tickfont: { size: 11 }
                    },
                    radialaxis:""",
    )
    html = html.replace(
        "                margin: { l: 40, r: 40, t: 50, b: 40 },",
        "                margin: { l: 84, r: 84, t: 50, b: 54 },",
    )
    impact_radar_js = r"""
            const impactValues = top5Local.map(f => Math.abs(radarValue(sample.contributions, f, 0)));
            const maxImpact = Math.max(...impactValues, 1e-9);
            const nImpact = impactValues.map(v => Math.max(0, Math.min(1, v / maxImpact)));
            if (nImpact.length > 0) nImpact.push(nImpact[0]);
            const impactCustom = top5Local.map((f, i) => {
                const contrib = radarValue(sample.contributions, f, 0);
                return [
                    formatRadarValue(rSampleVals[i], f, i),
                    formatRadarNumber(contrib, 2)
                ];
            });
            if (impactCustom.length > 0) impactCustom.push(impactCustom[0]);
            Plotly.react('local-radar', [{
                type: 'scatterpolar',
                r: nImpact,
                theta: theta,
                fill: 'toself',
                name: (typeof CURR_LANG !== 'undefined' && CURR_LANG === 'en' ? 'Local impact' : 'Impacto local'),
                line: { color: '#0e91c3', width: 3 },
                fillcolor: 'rgba(14,145,195,0.32)',
                customdata: impactCustom,
                hovertemplate: '%{theta}<br>' +
                    ((typeof mapLang === 'function' ? mapLang() : 'pt') === 'en' ? 'Real value' : 'Valor real') +
                    ': %{customdata[0]}<br>' +
                    ((typeof mapLang === 'function' ? mapLang() : 'pt') === 'en' ? 'EBM impact' : 'Impacto EBM') +
                    ': %{customdata[1]}<extra></extra>'
            }], {
                title: { text: (typeof CURR_LANG !== 'undefined' && CURR_LANG === 'pt' ? 'Força dos drivers locais' : 'Local driver strength'), font: { size: 14 } },
                polar: {
                    angularaxis: { tickfont: { size: 11 } },
                    radialaxis: {
                        visible: true,
                        range: [0, 1],
                        tickvals: [0, 0.25, 0.5, 0.75, 1],
                        showticklabels: false,
                        showline: false,
                        ticks: '',
                        gridcolor: 'rgba(0,0,0,0.1)'
                    }
                },
                showlegend: false,
                margin: { l: 84, r: 84, t: 50, b: 54 },
                font: { family: 'Inter, sans-serif' }
            }, { responsive: false, displayModeBar: false });

"""
    html = html.replace(
        "            renderTermGraphs(App.currentPolo.term_graphs, sample);",
        impact_radar_js + "            renderTermGraphs(App.currentPolo.term_graphs, sample);",
    )
    html = re.sub(
        r"        function renderTermGraphs\(graphs, sample\) \{.*?\n        function selectSample\(sample\) \{",
        r"""        function renderTermGraphs(graphs, sample) {
            const grid = $('term-grid');
            if (!grid) return;
            grid.style.display = 'grid';
            if (window.Plotly) {
                grid.querySelectorAll('.js-plotly-plot').forEach(div => {
                    try { Plotly.purge(div); } catch (e) { }
                });
            }
            grid.innerHTML = '';

            const normFeatureKey = value => String(value || '')
                .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
                .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
            const localFeatureAliases = {
                'Moradores em casas por célula': ['Moradores em casas', 'ibge_mediapopc'],
                'Moradores em casas': ['Moradores em casas por célula', 'ibge_mediapopc'],
                'Domicílios tipo casa': ['Domicílios em casas', 'Domicílios em casas por célula', 'ibge_mediadomc'],
                'Domicílios em casas': ['Domicílios tipo casa', 'Domicílios em casas por célula', 'ibge_mediadomc'],
                'Domicílios em casas por célula': ['Domicílios tipo casa', 'Domicílios em casas', 'ibge_mediadomc'],
                'Moradores por domicílio tipo casa': ['Moradores por casa', 'ibge_mediapopdomc'],
                'Moradores por casa': ['Moradores por domicílio tipo casa', 'ibge_mediapopdomc'],
                'Moradores em apartamentos por célula': ['Moradores por apartamento', 'ibge_mediapopa'],
                'Moradores por apartamento': ['Moradores em apartamentos por célula', 'ibge_mediapopdoma'],
                'Domicílios tipo apartamento': ['Domicílios tipo apartamento por célula', 'Domicílios em apartamentos', 'ibge_mediadoma'],
                'Domicílios tipo apartamento por célula': ['Domicílios tipo apartamento', 'Domicílios em apartamentos', 'ibge_mediadoma'],
                'Domicílios em apartamentos': ['Domicílios tipo apartamento', 'Domicílios tipo apartamento por célula', 'ibge_mediadoma']
            };
            const featureCandidates = (feat) => {
                const label = getLabel(feat);
                const out = [feat, label];
                [feat, label].forEach(k => (localFeatureAliases[k] || []).forEach(alias => out.push(alias)));
                if (App.currentPolo && App.currentPolo.feature_labels) {
                    Object.entries(App.currentPolo.feature_labels).forEach(([raw, lbl]) => {
                        const keys = [feat, label, ...(localFeatureAliases[feat] || []), ...(localFeatureAliases[label] || [])];
                        if (keys.includes(raw) || keys.includes(lbl) || keys.some(k => normFeatureKey(k) === normFeatureKey(raw) || normFeatureKey(k) === normFeatureKey(lbl))) {
                            out.push(raw, lbl);
                        }
                    });
                }
                return [...new Set(out.filter(Boolean))];
            };
            const resolveFeatureKey = (obj, feat) => {
                if (!obj) return null;
                const candidates = featureCandidates(feat);
                for (const key of candidates) {
                    if (Object.prototype.hasOwnProperty.call(obj, key)) return key;
                }
                const normalized = candidates.map(normFeatureKey);
                return Object.keys(obj).find(k => normalized.includes(normFeatureKey(k))) || null;
            };
            const featureValue = (feat) => {
                const key = resolveFeatureKey(sample && sample.values, feat);
                if (!key) return null;
                const value = Number(sample.values[key]);
                return Number.isFinite(value) ? value : null;
            };

            const featureContribution = (feat) => {
                const key = resolveFeatureKey(sample && sample.contributions, feat);
                if (!key) return null;
                const value = Number(sample.contributions[key]);
                return Number.isFinite(value) ? value : null;
            };

            const nearestCurveY = (xVals, yVals, xValue) => {
                let bestIdx = -1;
                let bestDiff = Infinity;
                xVals.forEach((x, idx) => {
                    const diff = Math.abs(Number(x) - Number(xValue));
                    if (Number.isFinite(diff) && diff < bestDiff) {
                        bestDiff = diff;
                        bestIdx = idx;
                    }
                });
                const y = bestIdx >= 0 ? Number(yVals[bestIdx]) : 0;
                return Number.isFinite(y) ? y : 0;
            };

            const radarGraphKeys = (window.__RF_LAST_RADAR_FEATURES__ || [])
                .map(feat => resolveFeatureKey(graphs || {}, feat))
                .filter(Boolean);
            const graphKeys = [...new Set([...radarGraphKeys, ...Object.keys(graphs || {})])]
                .filter(feat => !sample || featureValue(feat) !== null);
            if (!graphKeys.length) {
                grid.style.display = 'none';
                return;
            }

            graphKeys.forEach((feat, idx) => {
                const div = document.createElement('div');
                div.id = `chart-feat-${idx}`;
                div.className = 'mini-chart';
                grid.appendChild(div);

                const gData = graphs[feat];
                const traces = [];
                let commonX = Array.isArray(gData.x) ? gData.x.slice() : [];
                let commonY = Array.isArray(gData.y) ? gData.y.slice() : [];
                const density = Array.isArray(gData.density) ? gData.density.slice() : [];
                const minLen = Math.min(
                    commonX.length,
                    commonY.length,
                    density.length > 0 ? density.length : commonX.length
                );
                commonX = commonX.slice(0, minLen);
                commonY = commonY.slice(0, minLen);

                if (density.length > 0) {
                    traces.push({
                        x: commonX,
                        y: density.slice(0, commonX.length),
                        type: 'bar',
                        marker: { color: '#e0e0e0', opacity: 0.8 },
                        name: 'Density',
                        yaxis: 'y2',
                        hoverinfo: 'none'
                    });
                }

                if (gData.type === 'continuous') {
                    traces.push({
                        x: commonX,
                        y: commonY,
                        mode: 'lines',
                        type: 'scatter',
                        line: { shape: 'hv', color: '#2c3e50', width: 2 },
                        name: 'Risk Trend'
                    });
                } else {
                    traces.push({
                        x: commonX,
                        y: commonY,
                        type: 'bar',
                        marker: { color: '#bdc3c7' },
                        name: 'Probability Impact'
                    });
                }

                if (sample) {
                    const val = featureValue(feat);
                    if (val !== null) {
                        let contrib = featureContribution(feat);
                        if (contrib === null) contrib = nearestCurveY(commonX, commonY, val);
                        traces.push({
                            x: [val],
                            y: [contrib],
                            mode: 'markers',
                            type: 'scatter',
                            marker: {
                                size: 12,
                                color: contrib > 0 ? '#ff4b4b' : '#2ecc71',
                                line: { width: 2, color: 'white' }
                            },
                            name: 'Selected cell',
                            hovertemplate: `Impact: ${contrib.toFixed(3)}<br>Value: ${val}<extra></extra>`
                        });
                        traces.push({
                            x: [val, val],
                            y: [0, contrib],
                            mode: 'lines',
                            type: 'scatter',
                            line: { color: contrib > 0 ? '#ff4b4b' : '#2ecc71', width: 2, dash: 'dash' },
                            showlegend: false,
                            hoverinfo: 'none'
                        });
                    }
                }

                Plotly.newPlot(div.id, traces, {
                    title: { text: getLabel(feat), font: { size: 12, color: '#555' } },
                    margin: { t: 30, b: 30, l: 30, r: 30 },
                    showlegend: false,
                    xaxis: { showgrid: false },
                    yaxis: { title: 'Probability Impact', overlaying: 'y2' },
                    yaxis2: {
                        title: '',
                        showgrid: false,
                        showticklabels: false,
                        overlaying: 'free',
                        side: 'right',
                        position: 1,
                        type: 'linear',
                        range: [0, Math.max(...(density.length ? density : [1])) * 3]
                    },
                    font: { family: 'Inter, sans-serif' }
                }, { responsive: false, displayModeBar: false });
            });
        }

        function selectSample(sample) {""",
        html,
        count=1,
        flags=re.S,
    )
    html = html.replace(
        "      scope: p.a || '',\n      municipio: p.mu || ''\n    };",
        "      scope: p.a || '',\n"
        "      municipio: p.mu || '',\n"
        "      winner_scenario: p.w || '',\n"
        "      local_scenario: p.lw || p.w || '',\n"
        "      prob_completo: p.pc === null || p.pc === undefined ? null : Number(p.pc),\n"
        "      prob_morfologico: p.pm === null || p.pm === undefined ? null : Number(p.pm),\n"
        "      prob_nao_morfologico: p.pn === null || p.pn === undefined ? null : Number(p.pn)\n"
        "    };",
    )
    html = html.replace(
        "      intercept: (typeof App !== 'undefined' && App.currentPolo && App.currentPolo.intercept) ? App.currentPolo.intercept : 0,",
        "      intercept: (() => {\n"
        "        const areaIntercepts = (typeof FINAL_MODEL_INTERCEPTS !== 'undefined' && FINAL_MODEL_INTERCEPTS[p.a]) ? FINAL_MODEL_INTERCEPTS[p.a] : {};\n"
        "        const localIntercept = Number(areaIntercepts[p.lw || p.w || '']);\n"
        "        if (Number.isFinite(localIntercept)) return localIntercept;\n"
        "        return (typeof App !== 'undefined' && App.currentPolo && App.currentPolo.intercept) ? App.currentPolo.intercept : 0;\n"
        "      })(),",
    )
    helper = r"""
  function finalScenarioLabel(value) {
    const labels = {
      completo: mapLang() === 'en' ? 'Full model' : 'Modelo completo',
      morfologico: mapLang() === 'en' ? 'Morphological model' : 'Modelo morfolÃ³gico',
      nao_morfologico: mapLang() === 'en' ? 'Non-morphological model' : 'Modelo nÃ£o morfolÃ³gico'
    };
    return labels[value] || value || '-';
  }

  function winnerModelLabel() {
    return mapLang() === 'en' ? 'Area winning model' : 'Modelo vencedor da Ã¡rea';
  }

  function localModelLabel() {
    return mapLang() === 'en' ? 'Local explanation model' : 'Modelo da explicaÃ§Ã£o local';
  }

  function modelProbabilitiesHtml(sample, compact = false) {
    if (!sample) return '';
    const rows = [
      ['Completo', sample.prob_completo],
      ['MorfolÃ³gico', sample.prob_morfologico],
      ['NÃ£o morfolÃ³gico', sample.prob_nao_morfologico]
    ].filter(row => row[1] !== null && row[1] !== undefined && Number.isFinite(Number(row[1])));
    if (!rows.length) return '';
    if (compact) {
      return rows.map(row => `${row[0]}: <b>${percentLabel(row[1])}</b>`).join('<br>');
    }
    return `<div style="margin-top:6px;font-size:12px;line-height:1.35;color:#52636d;">` +
      rows.map(row => `${row[0]}: <b>${percentLabel(row[1])}</b>`).join(' &nbsp; ') +
      `</div>`;
  }

"""
    helper += r"""
  const FINAL_VISIBLE_CLASSES = {priority: true, attention: true, other: true, mappedAll: true, mappedFcu: true, mappedLow: true};

  function finalScenarioLabel(value) {
    const labels = {
      completo: mapLang() === 'en' ? 'Full model' : 'Modelo completo',
      morfologico: mapLang() === 'en' ? 'Morphological model' : 'Modelo morfolÃ³gico',
      nao_morfologico: mapLang() === 'en' ? 'Non-morphological model' : 'Modelo nÃ£o morfolÃ³gico'
    };
    return labels[value] || value || '-';
  }

  function winnerModelLabel() {
    return mapLang() === 'en' ? 'Area winning model' : 'Modelo vencedor da Ã¡rea';
  }

  function localModelLabel() {
    return mapLang() === 'en' ? 'Local explanation model' : 'Modelo da explicaÃ§Ã£o local';
  }

  function finalClassLabel(key) {
    const dict = {
      pt: {
        priority: 'atenÃ§Ã£o prioritÃ¡ria',
        attention: 'atenÃ§Ã£o',
        other: 'demais Ã¡reas',
        mappedAll: 'FCUs originais completas',
        mappedFcu: 'FCU original mantida',
        mappedLow: 'FCU original em revisÃ£o'
      },
      en: {
        priority: 'priority attention',
        attention: 'attention',
        other: 'other areas',
        mappedAll: 'all original FCU polygons',
        mappedFcu: 'original FCU maintained',
        mappedLow: 'original FCU for review'
      }
    };
    return (dict[mapLang()] && dict[mapLang()][key]) || key;
  }

  function finalClassVisible(key) {
    return FINAL_VISIBLE_CLASSES[key] !== false;
  }

  function maxModelProbFromSample(sample) {
    const vals = [
      Number(sample && sample.prob_completo),
      Number(sample && sample.prob_morfologico),
      Number(sample && sample.prob_nao_morfologico)
    ].filter(Number.isFinite);
    return vals.length ? Math.max(...vals) : Number(sample && sample.proba) || 0;
  }

  function maxModelProbFromPoint(p) {
    const vals = [Number(p && p.pc), Number(p && p.pm), Number(p && p.pn)].filter(Number.isFinite);
    return vals.length ? Math.max(...vals) : Number(p && p.p) || 0;
  }

  function fcuFeatureClass(feature) {
    const props = feature && feature.properties ? feature.properties : {};
    const prob = Number(props.prob_media_max_modelos);
    const low = props.aderencia_modelo === 'fcu_revisao' || (Number.isFinite(prob) && prob < 0.70);
    return low ? 'mappedLow' : 'mappedFcu';
  }

  function fcuOriginalBaseStyle(feature) {
    const key = fcuFeatureClass(feature);
    if (!finalClassVisible(key)) {
      return {color: '#111827', weight: 0, opacity: 0, fillOpacity: 0};
    }
    return {
      color: '#020617',
      weight: 2.2,
      fillColor: '#111827',
      fillOpacity: 0.24,
      opacity: 0.82
    };
  }

  function fcuOriginalPolygonStyle(feature) {
    const key = fcuFeatureClass(feature);
    if (!finalClassVisible(key)) {
      return {color: '#636363', weight: 0, opacity: 0, fillOpacity: 0};
    }
    const low = key === 'mappedLow';
    return {
      color: low ? '#4b5563' : '#1f2937',
      weight: low ? 2.4 : 2.8,
      fillColor: low ? '#bdbdbd' : '#4b5563',
      fillOpacity: low ? 0.72 : 0.66,
      opacity: 1
    };
  }

  function refreshFcuPolygonsStyle() {
    if (App.fcuBasePolygonsLayer) App.fcuBasePolygonsLayer.eachLayer(layer => {
      if (layer && layer.setStyle) layer.setStyle(fcuOriginalBaseStyle(layer.feature));
    });
    if (App.fcuPolygonsLayer) App.fcuPolygonsLayer.eachLayer(layer => {
      if (layer && layer.setStyle) layer.setStyle(fcuOriginalPolygonStyle(layer.feature));
    });
  }

  function modelProbabilityRows(sample) {
    if (!sample) return [];
    return [
      ['completo', finalScenarioLabel('completo'), sample.prob_completo],
      ['morfologico', finalScenarioLabel('morfologico'), sample.prob_morfologico],
      ['nao_morfologico', finalScenarioLabel('nao_morfologico'), sample.prob_nao_morfologico]
    ].filter(row => row[2] !== null && row[2] !== undefined && Number.isFinite(Number(row[2])));
  }

  function finalMergeSampleWithLocalExplanation(lightSample, point) {
    const id = String((lightSample && lightSample.id) || (point && point.id) || '');
    if (!id || typeof App === 'undefined' || !App.currentPolo) return lightSample;
    const full = (App.currentPolo.local_explanations || []).find(s => String(s.id || '') === id);
    if (!full) return lightSample;
    return {
      ...full,
      ...lightSample,
      values: {...(lightSample.values || {}), ...(full.values || {})},
      contributions: {...(lightSample.contributions || {}), ...(full.contributions || {})},
      intercept: Number.isFinite(Number(full.intercept)) ? Number(full.intercept) : lightSample.intercept,
      proba: Number.isFinite(Number(lightSample.proba)) ? lightSample.proba : full.proba,
      lat: Number.isFinite(Number(lightSample.lat)) ? lightSample.lat : full.lat,
      lng: Number.isFinite(Number(lightSample.lng)) ? lightSample.lng : full.lng,
      target: lightSample.target,
      ranking_candidato: lightSample.ranking_candidato,
      municipio: lightSample.municipio || full.municipio || '',
      scope: lightSample.scope || full.scope || (App.currentPolo ? App.currentPolo.area_col : ''),
      res_m: lightSample.res_m || full.res_m || 50
    };
  }

  function modelDisagreementHtml(sample, compact = false) {
    const rows = modelProbabilityRows(sample);
    if (!rows.length) return '';
    const best = rows.slice().sort((a, b) => Number(b[2]) - Number(a[2]))[0];
    const winnerProb = Number(sample && sample.proba) || 0;
    const isDifferent = best && best[0] !== sample.winner_scenario && Number(best[2]) - winnerProb >= 0.20;
    if (!isDifferent) return '';
    const label = mapLang() === 'en' ? 'Model disagreement' : 'DivergÃªncia entre modelos';
    const text = `${label}: ${best[1]} ${percentLabel(best[2])}`;
    if (compact) return `<span style="color:#b45309;">${escapeHtml(text)}</span><br>`;
    return `<div style="margin-top:6px;color:#b45309;font-size:12px;line-height:1.35;"><b>${escapeHtml(text)}</b></div>`;
  }

  function hasModelDisagreement(sample) {
    const rows = modelProbabilityRows(sample);
    if (!rows.length || Number(sample && sample.target) === 1) return false;
    const best = rows.slice().sort((a, b) => Number(b[2]) - Number(a[2]))[0];
    const winnerProb = Number(sample && sample.proba) || 0;
    return !!(best && best[0] !== sample.winner_scenario && Number(best[2]) >= 0.70 && winnerProb < 0.70 && Number(best[2]) - winnerProb >= 0.20);
  }

  function hasPointModelDisagreement(p) {
    if (Number(p.t) === 1) return false;
    const rows = [
      ['completo', Number(p.pc)],
      ['morfologico', Number(p.pm)],
      ['nao_morfologico', Number(p.pn)]
    ].filter(row => Number.isFinite(row[1]));
    if (!rows.length) return false;
    const best = rows.slice().sort((a, b) => b[1] - a[1])[0];
    const winnerProb = Number(p.p) || 0;
    return !!(best && best[0] !== p.w && best[1] >= 0.70 && winnerProb < 0.70 && best[1] - winnerProb >= 0.20);
  }

  function modelProbabilitiesHtml(sample, compact = false) {
    const rows = modelProbabilityRows(sample);
    if (!rows.length) return '';
    if (compact) {
      return rows.map(row => `${row[1]}: <b>${percentLabel(row[2])}</b>`).join('<br>');
    }
    return `<div style="margin-top:6px;font-size:12px;line-height:1.35;color:#52636d;">` +
      rows.map(row => `${row[1]}: <b>${percentLabel(row[2])}</b>`).join(' &nbsp; ') +
      `</div>`;
  }

"""
    html = html.replace("  function showPointPopup(sample) {", helper + "  function showPointPopup(sample) {")
    html = html.replace(
        "      `${mapText('probability')}: <b>${percentLabel(sample.proba)}</b><br>` +\n"
        "      `${mapText('candidateRank')}: <b>${rank}</b><br>` +",
        "      `${mapText('probability')}: <b>${percentLabel(sample.proba)}</b><br>` +\n"
        "      `${modelProbabilitiesHtml(sample, true)}<br>` +\n"
        "      `${mapText('candidateRank')}: <b>${rank}</b><br>` +",
    )
    html = html.replace(
        "          details.innerHTML = `${mapText('currentSelection')} <code>${escapeHtml(sample.id)}</code> ${mapText('withProbability')} <span style=\"color:var(--primary)\">${percentLabel(sample.proba)}</span>`;",
        "          details.innerHTML = `${mapText('currentSelection')} <code>${escapeHtml(sample.id)}</code> ${mapText('withProbability')} <span style=\"color:var(--primary)\">${percentLabel(sample.proba)}</span>${modelProbabilitiesHtml(sample)}`;",
    )
    html = html.replace(
        "    chip.innerText = `${prefix} - ${sample.id} (${percentLabel(sample.proba)})`;",
        "    chip.innerText = `${sample.id} (${percentLabel(sample.proba)})`;",
    )
    html = html.replace(
        "el.onclick = () => selectSample(sample);\n        return el;",
        "el.onclick = () => { selectSample(sample); showPointPopup(sample); };\n        return el;",
    )
    html = html.replace(
        "      selectSample(sample);\n      showPointPopup(sample);",
        "      const mergedSample = finalMergeSampleWithLocalExplanation(sample, point);\n"
        "      selectSample(mergedSample);\n"
        "      if (typeof loadFcusForCurrentArea === 'function') setTimeout(loadFcusForCurrentArea, 180);\n"
        "      showPointPopup(mergedSample);",
    )
    html = html.replace(
        "    if (target) return {color: '#3f3f46', radius: 1.1, alpha: 0.44, key: 'mappedFcu'};",
        "    if (target && maxModelProbFromPoint(p) < 0.70) return {color: 'transparent', radius: 0, alpha: 0, key: 'mappedLow'};\n"
        "    if (target) return {color: 'transparent', radius: 0, alpha: 0, key: 'mappedFcu'};",
    )
    html = html.replace(
        "return {color: '#e74c3c', radius: 1.45, alpha: 0.78, key: 'priority'};",
        "return {color: '#f03b20', radius: 1.90, alpha: 0.88, key: 'priority'};",
    )
    html = html.replace(
        "return {color: '#f39c12', radius: 1.35, alpha: 0.72, key: 'attention'};",
        "return {color: '#feb24c', radius: 1.70, alpha: 0.84, key: 'attention'};",
    )
    html = html.replace(
        "if (rank <= nFcu) return {color: '#feb24c', radius: 1.70, alpha: 0.84, key: 'attention'};",
        "if (rank <= nFcu * 2) return {color: '#feb24c', radius: 1.70, alpha: 0.84, key: 'attention'};",
    )
    html = html.replace(
        "if (rank <= nFcu) return mapText('attention');",
        "if (rank <= nFcu * 2) return mapText('attention');",
    )
    html = html.replace(
        "return {color: '#3498db', radius: 0.8, alpha: 0.035, key: 'other'};",
        "return {color: '#ffeda0', radius: 0.8, alpha: 0.045, key: 'other'};",
    )
    html = html.replace(
        "    if (areaName && !sameArea && typeof loadPolo === 'function') {\n"
        "      loadPolo(areaName);\n"
        "      setTimeout(openHere, 450);\n"
        "    } else {",
        "    if (areaName && !sameArea && typeof loadPolo === 'function') {\n"
        "      if (typeof App !== 'undefined') App.finalPendingPointOpen = true;\n"
        "      loadPolo(areaName);\n"
        "      setTimeout(() => {\n"
        "        if (typeof App !== 'undefined') App.finalPendingPointOpen = false;\n"
        "        openHere();\n"
        "      }, 520);\n"
        "    } else {",
    )
    html = html.replace(
        "    if (picks.length > 0) {\n"
        "      const currentId = (typeof App !== 'undefined' && App.selectedSample) ? String(App.selectedSample.id || '') : '';",
        "    if (typeof App !== 'undefined' && App.finalPendingPointOpen) return;\n\n"
        "    if (picks.length > 0) {\n"
        "      const currentId = (typeof App !== 'undefined' && App.selectedSample) ? String(App.selectedSample.id || '') : '';",
    )
    html = re.sub(
        r"  function pickBandSample\(pool, band, usedIds\) \{.*?\n  function refreshBandChipLabels",
        r"""  function pickBandSample(pool, band, usedIds) {
    const source = (pool || [])
      .filter(s => sampleId(s) && !usedIds.has(sampleId(s)) && sampleInBand(s, band))
      .sort((a, b) => (sampleProb(b) - sampleProb(a)) || sampleId(a).localeCompare(sampleId(b)));
    return source[0] || null;
  }

  function refreshBandChipLabels""",
        html,
        count=1,
        flags=re.S,
    )
    html = html.replace(
        "    } else {\n"
        "      if (candidates[0] || sorted[0]) selectSample(candidates[0] || sorted[0]);\n"
        "    }\n\n"
        "    const searchBox = document.getElementById('search-box');",
        "    } else {\n"
        "      const alt = fallbackPool.slice(0, 5);\n"
        "      alt.forEach(sample => suggestionArea.appendChild(createChip(sample, true)));\n"
        "      if (alt[0]) selectSample(alt[0]);\n"
        "    }\n\n"
        "    const searchBox = document.getElementById('search-box');",
    )
    html = html.replace(
        "    if (Number(sample.target) === 1) return mapText('mappedFcu');",
        "    if (Number(sample.target) === 1 && maxModelProbFromSample(sample) < 0.70) return finalClassLabel('mappedLow');\n"
        "    if (Number(sample.target) === 1) return finalClassLabel('mappedFcu');",
    )
    html = html.replace(
        "    L.popup({maxWidth: 280, closeButton: true})\n"
        "      .setLatLng([lat, lng])",
        "    L.popup({maxWidth: 320, closeButton: true, autoPan: true, keepInView: true, autoPanPadding: [70, 70], offset: L.point(0, -18)})\n"
        "      .setLatLng([lat, lng])",
    )
    html = html.replace(
        "    if (typeof App === 'undefined' || !App.map || App.map.getZoom() < TILE_Z) return;",
        "    if (e && e.originalEvent && typeof L !== 'undefined') L.DomEvent.stop(e.originalEvent);\n"
        "    if (typeof App === 'undefined' || !App.map || App.map.getZoom() < TILE_Z) return;",
    )
    html = html.replace(
        "          if (!cls.alpha || cls.alpha <= 0) continue;",
        "          if (!finalClassVisible(cls.key)) continue;\n"
        "          if (!cls.alpha || cls.alpha <= 0) continue;",
    )
    html = html.replace(
        """          ctx.beginPath();
          ctx.arc(x, y, cls.radius, 0, Math.PI * 2);
          ctx.fillStyle = cls.color;
          ctx.globalAlpha = cls.alpha;
          ctx.fill();""",
        """          const zoomBoost = Math.max(0, coords.z - TILE_Z);
          const drawRadius = cls.key === 'priority' || cls.key === 'attention'
            ? Math.min(9.5, cls.radius + zoomBoost * 0.78)
            : Math.min(2.3, cls.radius + zoomBoost * 0.16);
          ctx.beginPath();
          ctx.arc(x, y, drawRadius, 0, Math.PI * 2);
          ctx.fillStyle = cls.color;
          ctx.globalAlpha = cls.key === 'priority' || cls.key === 'attention'
            ? Math.max(0.62, cls.alpha - Math.min(0.16, zoomBoost * 0.02))
            : cls.alpha;
          ctx.fill();
          if (cls.key === 'priority' || cls.key === 'attention') {
            ctx.globalAlpha = Math.min(0.72, ctx.globalAlpha + 0.08);
            ctx.strokeStyle = cls.key === 'priority' ? 'rgba(90, 24, 16, 0.70)' : 'rgba(110, 70, 12, 0.62)';
            ctx.lineWidth = Math.max(1.1, Math.min(1.8, drawRadius * 0.18));
            ctx.stroke();
          }""",
    )
    html = html.replace(
        "App.allPointsLayer = new AllPointsLayer({tileSize: 256, opacity: 0.9, zIndex: 350});",
        "App.allPointsLayer = new AllPointsLayer({tileSize: 256, opacity: 0.92, zIndex: 460});",
    )
    html = html.replace(
        "        appendSampleLinks(sample);\n        setTimeout(() => {",
        "        appendSampleLinks(sample);\n"
        "        if (sample && typeof renderTermGraphs === 'function' && App.currentPolo && App.currentPolo.term_graphs) {\n"
        "          const rankedLocal = Object.entries(sample.contributions || {})\n"
        "            .sort((a, b) => Math.abs(Number(b[1]) || 0) - Math.abs(Number(a[1]) || 0))\n"
        "            .slice(0, 7)\n"
        "            .map(row => row[0]);\n"
        "          window.__RF_LAST_RADAR_FEATURES__ = rankedLocal;\n"
        "          renderTermGraphs(App.currentPolo.term_graphs, sample);\n"
        "        }\n"
        "        setTimeout(() => {",
    )
    html = html.replace(
        "        previousLoadPolo(name);\n        if (App.allPointsLayer) App.allPointsLayer.redraw();",
        "        previousLoadPolo(name);\n"
        "        renderBandSampleControls(App.currentPolo.local_explanations || []);\n"
        "        if (App.fcuCanvasLayer) App.fcuCanvasLayer.redraw();\n"
        "        if (App.allPointsLayer) App.allPointsLayer.redraw();",
    )
    html = re.sub(
        r"App\.fcuPolygonsLayer = L\.geoJSON\(null, \{\s+interactive: false,\s+style: \{.*?\},\s+onEachFeature",
        """App.fcuBasePolygonsLayer = L.geoJSON(null, {
                    interactive: false,
                    pane: 'fcuBasePane',
                    style: function (feature) {
                        return fcuOriginalBaseStyle(feature);
                    }
                });

                App.fcuPolygonsLayer = L.geoJSON(null, {
                    interactive: false,
                    pane: 'fcuStatusPane',
                    style: function (feature) {
                        return fcuOriginalPolygonStyle(feature);
                    },
                    onEachFeature""",
        html,
        count=1,
        flags=re.S,
    )
    html = html.replace(
        """                // Override initMap to include fcuPolygonsLayer
                const origInitMap = initMap;
                initMap = function () {
                    origInitMap();
                    if (!App.map.hasLayer(App.fcuPolygonsLayer)) {
                        App.fcuPolygonsLayer.addTo(App.map);
                    }
                };""",
        """                // Override initMap to include FCU base/status polygon layers
                const origInitMap = initMap;
                initMap = function () {
                    origInitMap();
                    if (!App.map.getPane('fcuBasePane')) {
                        App.map.createPane('fcuBasePane');
                        App.map.getPane('fcuBasePane').style.zIndex = 335;
                        App.map.getPane('fcuBasePane').style.pointerEvents = 'none';
                    }
                    if (!App.map.getPane('fcuStatusPane')) {
                        App.map.createPane('fcuStatusPane');
                        App.map.getPane('fcuStatusPane').style.zIndex = 345;
                        App.map.getPane('fcuStatusPane').style.pointerEvents = 'none';
                    }
                    if (App.fcuBasePolygonsLayer && !App.map.hasLayer(App.fcuBasePolygonsLayer)) {
                        App.fcuBasePolygonsLayer.addTo(App.map);
                    }
                    if (App.fcuPolygonsLayer && !App.map.hasLayer(App.fcuPolygonsLayer)) {
                        App.fcuPolygonsLayer.addTo(App.map);
                    }
                };""",
    )
    html = re.sub(
        r"  function allPointsLegendHtml\(open\) \{.*?\n  function bindLegendToggle",
        r"""  function allPointsLegendHtml(open) {
    const dot = (color, alpha = 1) => `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};opacity:${alpha};margin-right:6px;vertical-align:middle;"></span>`;
    const fill = (color, border = '#636363', alpha = 1) => `<span style="display:inline-block;width:13px;height:10px;border-radius:2px;background:${color};border:2px solid ${border};opacity:${alpha};margin-right:6px;vertical-align:middle;"></span>`;
    const rows = [
      ['priority', dot('#f03b20', 1)],
      ['attention', dot('#feb24c', .95)],
      ['other', dot('#ffeda0', .65)],
      ['mappedFcu', fill('#4b5563', '#1f2937', .98)],
      ['mappedLow', fill('#bdbdbd', '#4b5563', 1)]
    ];
    return (
      `<div style="display:flex;align-items:center;gap:8px;padding:0.45rem 0.6rem 0.25rem 0.6rem;">` +
      `<button type="button" class="legend-toggle" style="border:0;background:transparent;padding:0;font:700 12px Inter,sans-serif;color:#2c3e50;cursor:pointer;text-align:left;flex:1;">${mapText('legend')}</button>` +
      `</div>` +
      `<div class="legend-body" style="display:${open ? 'block' : 'none'};padding:0 0.65rem 0.55rem 0.65rem;line-height:1.35;min-width:225px;">` +
      rows.map(row => {
        const active = FINAL_VISIBLE_CLASSES[row[0]] !== false;
        return `<div class="legend-filter" data-class="${row[0]}" title="mostrar/ocultar" style="cursor:pointer;pointer-events:auto;opacity:${active ? 1 : .42};padding:3px 4px;border-radius:5px;background:${active ? 'transparent' : '#edf2f7'};text-decoration:${active ? 'none' : 'line-through'};">${row[1]}${finalClassLabel(row[0])}</div>`;
      }).join('') +
      `</div>`
    );
  }

  function bindLegendToggle""",
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(r"\n  function winnerModelLabel\(\) \{.*?\n  \}\n", "\n", html, flags=re.S)
    html = re.sub(r"\n  function localModelLabel\(\) \{.*?\n  \}\n", "\n", html, flags=re.S)
    html = re.sub(
        r"\n  function modelDisagreementHtml\(sample, compact = false\) \{.*?\n  function hasModelDisagreement",
        "\n  function hasModelDisagreement",
        html,
        flags=re.S,
    )
    html = re.sub(
        r"\n  function hasModelDisagreement\(sample\) \{.*?\n  function hasPointModelDisagreement",
        "\n  function hasPointModelDisagreement",
        html,
        flags=re.S,
    )
    html = re.sub(
        r"  function bindLegendToggle\(div\) \{.*?\n  function refreshAllPointsLegend",
        r"""  function bindLegendToggle(div) {
    const refreshFilteredLayers = () => {
      if (App.overviewLayer && App.overviewLayer.setOpacity) {
        App.overviewLayer.setOpacity(0.95);
      }
      if (App.fcuCanvasLayer) App.fcuCanvasLayer.redraw();
      if (App.allPointsLayer) App.allPointsLayer.redraw();
      refreshFcuPolygonsStyle();
    };
    const toggleBody = () => {
      const body = div.querySelector('.legend-body');
      if (!body) return;
      body.style.display = body.style.display === 'none' ? 'block' : 'none';
    };
    const btn = div.querySelector('.legend-toggle');
    if (btn) btn.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      toggleBody();
    });
    const refreshBtn = div.querySelector('.legend-refresh');
    if (refreshBtn) refreshBtn.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      refreshFilteredLayers();
    });
    div.querySelectorAll('.legend-filter').forEach(item => {
      item.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        const key = item.dataset.class;
        FINAL_VISIBLE_CLASSES[key] = FINAL_VISIBLE_CLASSES[key] === false;
        refreshAllPointsLegend();
        refreshFilteredLayers();
      });
    });
  }

  function refreshAllPointsLegend""",
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(
        r"  function loadFcusForCurrentArea\(\) \{.*?\n  function handleAllPointsClick",
        r"""  function loadFcusForCurrentArea() {
    window.__RF_FCU_DEBUG__ = {
      called: true,
      hasApp: typeof App !== 'undefined',
      hasCurrentPolo: typeof App !== 'undefined' && !!App.currentPolo,
      hasLayer: typeof App !== 'undefined' && !!App.fcuPolygonsLayer
    };
    if (typeof App === 'undefined' || !App.fcuPolygonsLayer) return;
    if (!fcuDataPromise) {
      fcuDataPromise = fetch(FCU_URL).then(r => r.ok ? r.json() : {type:'FeatureCollection', features:[]});
    }
    const areaCol = (App.currentPolo && App.currentPolo.area_col) ||
      (App.selectedSample && App.selectedSample.scope) ||
      (App.currentPoloName && App.data && App.data[App.currentPoloName] ? App.data[App.currentPoloName].area_col : null);
    if (!areaCol) return;
    if (App.map) {
      if (App.fcuBasePolygonsLayer && !App.map.hasLayer(App.fcuBasePolygonsLayer)) App.fcuBasePolygonsLayer.addTo(App.map);
      if (App.fcuPolygonsLayer && !App.map.hasLayer(App.fcuPolygonsLayer)) App.fcuPolygonsLayer.addTo(App.map);
    }
    const layerCount = App.fcuPolygonsLayer && App.fcuPolygonsLayer.getLayers ? App.fcuPolygonsLayer.getLayers().length : 0;
    if (App.__fcuLoadedArea === areaCol && layerCount > 0) {
      refreshFcuPolygonsStyle();
      return;
    }
    fcuDataPromise.then(data => {
      const features = (data.features || []).filter(f => f.properties && f.properties.area_col === areaCol);
      window.__RF_FCU_DEBUG__ = {
        areaCol,
        totalFeatures: (data.features || []).length,
        visibleFeatures: features.length,
        currentPoloName: App.currentPoloName || null
      };
      App.__fcuLoadedArea = areaCol;
      if (App.fcuBasePolygonsLayer) {
        App.fcuBasePolygonsLayer.clearLayers();
        App.fcuBasePolygonsLayer.addData({type:'FeatureCollection', features});
      }
      App.fcuPolygonsLayer.clearLayers();
      App.fcuPolygonsLayer.addData({type:'FeatureCollection', features});
      refreshFcuPolygonsStyle();
    }).catch(error => {
      window.__RF_FCU_DEBUG__ = {areaCol, error: String(error && error.message ? error.message : error)};
    });
  }

  function handleAllPointsClick""",
        html,
        count=1,
        flags=re.S,
    )
    html = html.replace(
        "App.allPointsControl = L.control({position: 'topright'});",
        "App.allPointsControl = L.control({position: 'bottomleft'});",
    )
    html = html.replace(
        "div.innerHTML = allPointsLegendHtml(false);",
        "div.innerHTML = allPointsLegendHtml(false);",
    )
    html = html.replace(
        "const navKeys = ['navHome', 'navFull', 'navMorph', 'navAnalysis', 'navMore'];",
        "const navKeys = ['navHome', 'navMore'];",
    )
    html = html.replace(
        "App.map.on('click', handleAllPointsClick);",
        "App.map.options.closePopupOnClick = true;\n"
        "        if (App.map.doubleClickZoom) App.map.doubleClickZoom.enable();\n"
        "        let finalSingleClickTimer = null;\n"
        "        const clearFinalSingleClick = () => {\n"
        "          if (finalSingleClickTimer) clearTimeout(finalSingleClickTimer);\n"
        "          finalSingleClickTimer = null;\n"
        "        };\n"
        "        App.map.on('click', event => {\n"
        "          clearFinalSingleClick();\n"
        "          finalSingleClickTimer = setTimeout(() => {\n"
        "            finalSingleClickTimer = null;\n"
        "            handleAllPointsClick(event);\n"
        "          }, 260);\n"
        "        });\n"
        "        App.map.on('dblclick', clearFinalSingleClick);",
    )
    html = html.replace(
        "      ensureOverviewLayer();\n      refreshTouchInteractionGates();",
        "      ensureOverviewLayer();\n"
        "      if (!App.fcuCanvasLayer) {\n"
        "        App.fcuCanvasLayer = new FinalFcuCanvasLayer({tileSize: 256, opacity: 0.98, zIndex: 360});\n"
        "        App.fcuCanvasLayer.addTo(App.map);\n"
        "      } else if (!App.map.hasLayer(App.fcuCanvasLayer)) {\n"
        "        App.fcuCanvasLayer.addTo(App.map);\n"
        "      }\n"
        "      refreshTouchInteractionGates();",
    )
    html = html.replace(
        "        Plotly.relayout(radar, {'title.text': mapText('localDrivers')});",
        "        Plotly.relayout(radar, {'title.text': lang === 'en' ? 'Local driver strength' : 'Força dos drivers locais'});",
    )
    html = html.replace(
        "        if (App.allPointsLayer) App.allPointsLayer.redraw();\n        loadFcusForCurrentArea();",
        "        if (App.fcuCanvasLayer) App.fcuCanvasLayer.redraw();\n"
        "        if (App.allPointsLayer) App.allPointsLayer.redraw();\n"
        "        loadFcusForCurrentArea();",
    )
    html = html.replace(
        "      if (App.allPointsLayer) App.allPointsLayer.redraw();\n      setTimeout(bindFeatureClickHandlers, 260);",
        "      if (App.fcuCanvasLayer) App.fcuCanvasLayer.redraw();\n"
        "      if (App.allPointsLayer) App.allPointsLayer.redraw();\n"
        "      setTimeout(bindFeatureClickHandlers, 260);",
    )
    html = html.replace(
        "  patchMapWhenReady();",
        "  patchMapWhenReady();\n"
        "  let finalFcuLastArea = null;\n"
        "  function finalEnsureFcus() {\n"
        "    if (typeof App === 'undefined' || typeof loadFcusForCurrentArea !== 'function') return;\n"
        "    const areaCol = (App.currentPolo && App.currentPolo.area_col) ||\n"
        "      (App.selectedSample && App.selectedSample.scope) ||\n"
        "      (App.currentPoloName && App.data && App.data[App.currentPoloName] ? App.data[App.currentPoloName].area_col : null);\n"
        "    const layerCount = App.fcuPolygonsLayer && App.fcuPolygonsLayer.getLayers ? App.fcuPolygonsLayer.getLayers().length : 0;\n"
        "    if (areaCol && (areaCol !== finalFcuLastArea || layerCount === 0)) {\n"
        "      finalFcuLastArea = areaCol;\n"
        "      loadFcusForCurrentArea();\n"
        "    }\n"
        "  }\n"
        "  setTimeout(finalEnsureFcus, 800);\n"
        "  setInterval(finalEnsureFcus, 1200);",
    )
    nav_patch = r"""
<script>
(function() {
  function fixFinalHeader() {
    const nav = document.querySelector('.site-nav-links');
    if (nav) {
      nav.innerHTML =
        '<a class="active" href="index.html">InÃ­cio</a>' +
        '<a href="https://cefavela.ufabc.edu.br/revelando-favelas-arcabouco-metodologico-para-identificacao-e-caracterizacao-de-favelas/" target="_blank" rel="noopener noreferrer">Saiba mais</a>';
    }
    const title = document.querySelector('#dashboard-content header h1');
    if (title) title.textContent = 'Preditor FCU - resultado final';
  }
  let tries = 0;
  fixFinalHeader();
  const timer = setInterval(() => {
    fixFinalHeader();
    tries += 1;
    if (tries > 12) clearInterval(timer);
  }, 250);
})();
</script>
"""
    nav_patch += r"""
<script>
(function() {
  function finalNavLabels() {
    const en = window.CURR_LANG === 'en' || (window.rfSafeStorage && window.rfSafeStorage.getItem('revelando_lang') === 'en');
    return en
      ? ['Home', 'Model', 'Model analysis', 'Learn more', 'FCU Predictor - final result']
      : ['InÃ­cio', 'Modelo', 'AnÃ¡lise dos modelos', 'Saiba mais', 'Preditor FCU - resultado final'];
  }
  function fixFinalNavigation() {
    const labels = finalNavLabels();
    const nav = document.querySelector('.site-nav-links');
    if (nav) {
      nav.innerHTML =
        `<a class="active" href="index.html">${labels[0]}</a>` +
        `<a href="https://cefavela.ufabc.edu.br/revelando-favelas-arcabouco-metodologico-para-identificacao-e-caracterizacao-de-favelas/" target="_blank" rel="noopener noreferrer">${labels[3]}</a>`;
    }
    const title = document.querySelector('#dashboard-content header h1');
    if (title) title.textContent = labels[4];
  }
  const previousApply = typeof applyEbmTranslations === 'function' ? applyEbmTranslations : null;
  if (previousApply) {
    applyEbmTranslations = function() {
      previousApply();
      fixFinalNavigation();
    };
  }
  const previousSet = typeof setLang === 'function' ? setLang : null;
  if (previousSet) {
    setLang = function(lang) {
      previousSet(lang);
      setTimeout(fixFinalNavigation, 80);
    };
  }
  fixFinalNavigation();
})();
</script>
"""
    return html.replace("</body>", nav_patch + "\n</body>")


def render_source_style_html() -> str:
    html = SOURCE_TEMPLATE_HTML.read_text(encoding="utf-8")
    payload = build_winner_payload()
    return inject_final_dashboard_patches(html, payload)


def render_html(manifest: dict[str, Any], downloads: list[dict[str, Any]]) -> str:
    area_options = "\n".join(
        f'<option value="{area_col}">{label}</option>'
        for label, area_col in AREA_ORDER
    )
    def size_label(value: Any) -> str:
        return f"{float(value):,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")

    download_links = "\n".join(
        f'<li><a href="downloads/{item["file"]}">{item["label"]}</a> '
        f'<span>{size_label(item["size_mb"])} MB</span></li>'
        for item in downloads
    )
    generated = datetime.now().strftime("%d/%m/%Y %H:%M")
    bounds = json.dumps(manifest.get("bounds", [-52.6, -26.0, -38.1, 1.0]))
    fcu_counts = json.dumps(manifest.get("fcu_counts", {}), ensure_ascii=False)
    scenario_labels = json.dumps(SCENARIO_LABELS, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Preditor FCU - Resultado Final</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root{{--primary:#2c3e50;--accent:#2563eb;--cyan:#2aa7c8;--bg:#f8f9fa;--border:#e5e7eb;--muted:#64748b;--danger:#e74c3c;--warn:#f39c12;--blue:#3498db;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
*{{box-sizing:border-box}}body{{margin:0;color:var(--primary);background:var(--bg)}}a{{color:inherit}}
.container{{width:min(1420px,calc(100% - 28px));margin:auto;padding:18px 0}}
.hero,.panel,.site-nav{{background:#fff;border:1px solid var(--border);border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.04)}}
.hero{{padding:22px;margin-bottom:12px}}.kicker{{font-size:.76rem;font-weight:800;color:#637481;text-transform:uppercase;letter-spacing:.06em}}
h1{{font-size:1.8rem;letter-spacing:0;margin:7px 0}}h2{{font-size:1.02rem;margin:0 0 10px}}p{{line-height:1.48}}.muted{{color:var(--muted)}}
.site-nav{{display:flex;gap:8px;flex-wrap:wrap;padding:10px;margin-bottom:14px}}.site-nav a{{border:1px solid #d8dee6;border-radius:6px;padding:8px 12px;text-decoration:none;background:#f8fafc;font-weight:650;font-size:.86rem}}.site-nav a.active{{color:#fff;background:var(--primary);border-color:var(--primary)}}
.layout{{display:grid;grid-template-columns:320px minmax(0,1fr) 360px;gap:12px;align-items:stretch}}.panel{{padding:14px;min-width:0}}
#map{{height:calc(100vh - 178px);min-height:620px;border-radius:8px;border:1px solid var(--border);overflow:hidden;background:#eef3f6}}
label{{display:block;font-size:.75rem;font-weight:800;color:var(--muted);text-transform:uppercase;margin:12px 0 5px}}select,input,button{{width:100%;border:1px solid #d8dee6;border-radius:6px;padding:9px 10px;background:#fff;color:var(--primary);font:inherit}}button{{cursor:pointer;font-weight:750;background:#f8fafc}}button.primary{{background:var(--primary);border-color:var(--primary);color:#fff}}
.legend{{display:grid;gap:7px;margin-top:12px}}.legend div{{display:flex;gap:8px;align-items:center;font-size:.86rem}}.swatch{{width:14px;height:14px;border-radius:3px;display:inline-block;border:1px solid rgba(0,0,0,.16)}}
.stat-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}}.stat{{border:1px solid var(--border);background:#fbfcfc;padding:9px;border-radius:6px}}.stat span{{display:block;font-size:.72rem;color:var(--muted)}}.stat strong{{font-size:1.14rem}}
.candidate-list{{display:grid;gap:7px;max-height:330px;overflow:auto;margin-top:8px}}.candidate{{border:1px solid var(--border);border-radius:6px;background:#fff;padding:8px;text-align:left}}.candidate strong{{display:block}}.candidate span{{font-size:.78rem;color:var(--muted)}}
.details-empty{{display:grid;place-items:center;min-height:220px;color:var(--muted);text-align:center;border:1px dashed var(--border);border-radius:8px;padding:16px}}
.prob-row{{display:grid;grid-template-columns:130px 1fr 52px;gap:8px;align-items:center;margin:7px 0}}.bar{{height:8px;background:#edf1f3;border-radius:99px;overflow:hidden}}.bar i{{display:block;height:100%;background:var(--cyan)}}
.tag{{display:inline-flex;border:1px solid var(--border);border-radius:999px;padding:3px 8px;background:#f8fafc;font-size:.76rem;margin:2px 3px 2px 0}}
.why{{display:grid;gap:7px;margin-top:8px}}.why-row{{border:1px solid var(--border);border-radius:6px;padding:8px;background:#fff}}.why-row b{{display:block;font-size:.88rem}}.why-row span{{font-size:.76rem;color:var(--muted)}}
.downloads{{font-size:.84rem;line-height:1.45;padding-left:18px}}.downloads li{{margin:6px 0}}.downloads span{{color:var(--muted);margin-left:5px}}
.leaflet-popup-content{{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--primary)}}
@media(max-width:1120px){{.layout{{grid-template-columns:1fr}}#map{{height:72vh;min-height:520px}}}}
</style>
</head>
<body>
<main class="container">
<header class="hero"><div class="kicker">Projeto Revelando Favelas</div><h1>Preditor FCU - resultado final</h1><p class="muted">Mapa para priorizar novas verificaÃ§Ãµes de FCU. A probabilidade exibida Ã© sempre a saÃ­da final do modelo vencedor em cada Ã¡rea de estudo. Atualizado em {generated}.</p></header>
<nav class="site-nav"><a class="active" href="index.html">Resultado final</a><a href="../05_dashboard/index.html">Dashboard tÃ©cnico</a><a href="https://cefavela.ufabc.edu.br/revelando-favelas-arcabouco-metodologico-para-identificacao-e-caracterizacao-de-favelas/" target="_blank" rel="noopener">Saiba mais</a></nav>
<section class="layout">
<aside class="panel">
<h2>Encontrar novas FCUs</h2>
<p class="muted">Use o ranking de candidatos para investigar cÃ©lulas sem FCU mapeada que receberam alta probabilidade final.</p>
<label for="areaSelect">Ãrea de estudo</label><select id="areaSelect"><option value="">Todas as Ã¡reas</option>{area_options}</select>
<label for="searchBox">Buscar cÃ©lula por ID</label><input id="searchBox" placeholder="Digite o ID da cÃ©lula"><button id="searchButton" class="primary" style="margin-top:8px">Buscar</button>
<div class="stat-grid">
<div class="stat"><span>CÃ©lulas</span><strong>{manifest.get("point_count", 0):,}</strong></div>
<div class="stat"><span>Tiles</span><strong>{manifest.get("tile_count", 0):,}</strong></div>
</div>
<div class="legend">
<div><i class="swatch" style="background:#f03b20"></i> Prioridade de campo</div>
<div><i class="swatch" style="background:#feb24c"></i> AtenÃ§Ã£o</div>
<div><i class="swatch" style="background:#ffeda055"></i> Demais candidatos</div>
<div><i class="swatch" style="background:#3f3f4688"></i> FCU mapeada com alta aderÃªncia</div>
<div><i class="swatch" style="background:#e67e2288"></i> FCU mapeada com baixa aderÃªncia (&lt;70%)</div>
</div>
<label>Top candidatos da Ã¡rea</label><div id="candidateList" class="candidate-list"></div>
</aside>
<section class="panel"><div id="map"></div></section>
<aside class="panel">
<h2>Por que olhar aqui?</h2>
<div id="details" class="details-empty">Clique em uma cÃ©lula no mapa para ver probabilidade, ranking e variÃ¡veis explicativas.</div>
<label>Produtos tÃ©cnicos locais</label><ul class="downloads">{download_links}</ul>
<p class="muted" style="font-size:.78rem">A pasta de downloads Ã© local e fica fora do deploy Vercel para manter o site leve.</p>
</aside>
</section>
</main>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const BOUNDS = {bounds};
const FCU_COUNTS = {fcu_counts};
const SCENARIO_LABELS = {scenario_labels};
const TILE_Z = {POINT_ZOOM};
const TOP_CANDIDATES_PER_AREA = {TOP_CANDIDATES_PER_AREA};
const OVERVIEW_URL = 'data_tiles/final/overview/{{z}}/{{x}}/{{y}}.png';
const POINT_URL = 'data_tiles/final/points/' + TILE_Z + '/{{x}}/{{y}}.json.gz';
const LOOKUP_PREFIX = {ID_LOOKUP_PREFIX_LEN};
const LOOKUP_BASE = 'data_tiles/final/id_lookup/' + LOOKUP_PREFIX;
let selectedArea = '';
let selectedPoint = null;
const tileCache = new Map();
const topCandidatesPromise = fetch('data_tiles/final/top_candidates.json').then(r => r.json()).catch(() => ({{}}));

const map = L.map('map', {{preferCanvas:true, minZoom:5, maxZoom:18}});
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{maxZoom:19, attribution:'&copy; OpenStreetMap'}}).addTo(map);
L.tileLayer(OVERVIEW_URL, {{minZoom:5, maxZoom:TILE_Z-1, minNativeZoom:6, maxNativeZoom:TILE_Z-1, opacity:.94, errorTileUrl:'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='}}).addTo(map);
map.fitBounds([[BOUNDS[1], BOUNDS[0]], [BOUNDS[3], BOUNDS[2]]]);

function pct(v) {{ return ((Number(v)||0)*100).toLocaleString('pt-BR', {{minimumFractionDigits:2, maximumFractionDigits:2}}) + '%'; }}
function esc(v) {{ return String(v ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch])); }}
function scenarioLabel(v) {{ return SCENARIO_LABELS[v] || v || '-'; }}
function fcuCount(area) {{ return Number(FCU_COUNTS[area] || 0); }}
function classOf(p) {{
  const target = Number(p.t)||0, rank = Number(p.r), n = fcuCount(p.a), prob = Number(p.p)||0;
  if (target && prob < {FCU_LOW_PROB_THRESHOLD}) return {{color:'#e67e22', alpha:.62, r:4, label:'FCU mapeada com baixa aderÃªncia'}};
  if (target) return {{color:'#3f3f46', alpha:.55, r:3.8, label:'FCU mapeada'}};
  if (Number.isFinite(rank) && rank > 0 && n > 0 && rank <= Math.ceil(n/2)) return {{color:'#f03b20', alpha:.90, r:6.2, label:'prioridade de campo'}};
  if (Number.isFinite(rank) && rank > 0 && n > 0 && rank <= n * 2) return {{color:'#feb24c', alpha:.86, r:5.6, label:'atenÃ§Ã£o'}};
  return {{color:'#ffeda0', alpha:.12, r:2.5, label:'demais candidatos'}};
}}
async function fetchJsonMaybeGzip(url) {{
  const key = url;
  if (tileCache.has(key)) return tileCache.get(key);
  const promise = fetch(url).then(r => {{
    if (!r.ok) return {{p:[]}};
    if ((r.headers.get('content-encoding')||'').toLowerCase().includes('gzip')) return r.json();
    if ('DecompressionStream' in window) return r.arrayBuffer().then(buf => new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'))).json());
    return r.json();
  }}).catch(() => ({{p:[]}}));
  tileCache.set(key, promise);
  return promise;
}}
const CandidateLayer = L.GridLayer.extend({{
  createTile: function(coords, done) {{
    const tile = L.DomUtil.create('canvas', 'leaflet-tile');
    tile.width = tile.height = 256;
    const ctx = tile.getContext('2d');
    fetchJsonMaybeGzip(POINT_URL.replace('{{x}}', coords.x).replace('{{y}}', coords.y)).then(data => {{
      for (const p of data.p || []) {{
        if (selectedArea && p.a !== selectedArea) continue;
        const st = classOf(p);
        ctx.globalAlpha = st.alpha;
        ctx.fillStyle = st.color;
        ctx.beginPath();
        ctx.arc(Number(p.x)||0, Number(p.y)||0, st.r, 0, Math.PI*2);
        ctx.fill();
      }}
      ctx.globalAlpha = 1;
      done(null, tile);
    }});
    return tile;
  }}
}});
const candidateLayer = new CandidateLayer({{minZoom:TILE_Z, maxZoom:18, tileSize:256, opacity:1}});
candidateLayer.addTo(map);

let fcuLayer = null;
fetch('data_tiles/fcu_aderencia.geojson').then(r => r.json()).then(data => {{
  fcuLayer = L.geoJSON(data, {{
    style: f => {{
      const prob = Number(f.properties.prob_media_winner);
      const low = Number.isFinite(prob) && prob < {FCU_LOW_PROB_THRESHOLD};
      return {{color: low ? '#e67e22' : '#3f3f46', weight: low ? 1.2 : .9, opacity: low ? .9 : .55, fillColor: low ? '#f5b7b1' : '#3f3f46', fillOpacity: low ? .24 : .12}};
    }},
    filter: f => !selectedArea || f.properties.area_col === selectedArea,
    onEachFeature: (f, layer) => {{
      const p = f.properties || {{}};
      layer.bindPopup(`<b>${{esc(p.nm_fcu || p.cd_fcu || p.id_fcu || 'FCU mapeada')}}</b><br>Probabilidade mÃ©dia final: <b>${{Number.isFinite(Number(p.prob_media_winner)) ? pct(p.prob_media_winner) : '-'}}</b><br>AderÃªncia: <b>${{esc(p.aderencia_modelo || '-')}}</b>`);
    }}
  }}).addTo(map);
}});

function tileCoord(lat, lng, z) {{
  const n = 2 ** z, latRad = lat * Math.PI / 180;
  const xf = (lng + 180) / 360 * n;
  const yf = (1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * n;
  return {{x:Math.floor(xf), y:Math.floor(yf), px:(xf-Math.floor(xf))*256, py:(yf-Math.floor(yf))*256}};
}}
async function nearestPoint(latlng) {{
  const c = tileCoord(latlng.lat, latlng.lng, TILE_Z);
  const data = await fetchJsonMaybeGzip(POINT_URL.replace('{{x}}', c.x).replace('{{y}}', c.y));
  let best = null, bestD = Infinity;
  for (const p of data.p || []) {{
    if (selectedArea && p.a !== selectedArea) continue;
    const d = Math.hypot((Number(p.x)||0)-c.px, (Number(p.y)||0)-c.py);
    if (d < bestD) {{ best = p; bestD = d; }}
  }}
  return bestD <= 14 ? best : null;
}}
function parseWhy(p) {{
  return String(p.rk || '').split(';').filter(Boolean).map(part => {{
    const bits = part.split(',');
    return {{feat: bits[0] || '', score: Number(bits[1]) || 0, value: bits.slice(2).join(',')}};
  }});
}}
function renderDetails(p) {{
  selectedPoint = p;
  const cls = classOf(p);
  const rank = p.r == null ? '-' : Number(p.r).toLocaleString('pt-BR');
  const why = parseWhy(p).map(row => `<div class="why-row"><b>${{esc(row.feat)}}</b><span>ContribuiÃ§Ã£o: ${{row.score.toLocaleString('pt-BR', {{maximumFractionDigits:3}})}} Â· Valor: ${{esc(row.value)}}</span></div>`).join('');
  document.getElementById('details').className = '';
  document.getElementById('details').innerHTML = `
    <div><span class="tag">${{esc(cls.label)}}</span><span class="tag">${{esc(scenarioLabel(p.w))}}</span><span class="tag">quintil ${{esc(p.q || '-')}}</span><span class="tag">classe ${{esc(p.rc || '-')}}</span></div>
    <h2 style="margin-top:10px">${{esc(p.id)}}</h2>
    <p class="muted">${{esc(p.mu || '')}} Â· ${{esc(p.al || p.a || '')}}</p>
    <div class="stat-grid"><div class="stat"><span>Probabilidade final</span><strong>${{pct(p.p)}}</strong></div><div class="stat"><span>Ranking candidato</span><strong>${{rank}}</strong></div></div>
    <label>Probabilidades dos modelos</label>
    ${{probLine('Completo', p.pc)}}${{probLine('MorfolÃ³gico', p.pm)}}${{probLine('NÃ£o morfolÃ³gico', p.pn)}}
    <label>Por que o modelo indicou essa cÃ©lula?</label><div class="why">${{why || '<p class="muted">Sem explicaÃ§Ã£o local disponÃ­vel para esta cÃ©lula.</p>'}}</div>
    <label>Abrir em mapa externo</label><p><a href="https://www.google.com/maps/search/?api=1&query=${{p.lat}},${{p.lng}}" target="_blank" rel="noopener">Google Maps</a> Â· <a href="https://www.openstreetmap.org/?mlat=${{p.lat}}&mlon=${{p.lng}}#map=18/${{p.lat}}/${{p.lng}}" target="_blank" rel="noopener">OpenStreetMap</a></p>`;
}}
function probLine(label, value) {{
  const width = Math.max(0, Math.min(100, (Number(value)||0)*100));
  return `<div class="prob-row"><span>${{label}}</span><div class="bar"><i style="width:${{width}}%"></i></div><b>${{pct(value)}}</b></div>`;
}}
function showPopup(p) {{
  const html = `<b>${{esc(p.id)}}</b><br>Probabilidade final: <b>${{pct(p.p)}}</b><br>Modelo usado: <b>${{esc(scenarioLabel(p.w))}}</b><br>Ranking candidato: <b>${{p.r == null ? '-' : Number(p.r).toLocaleString('pt-BR')}}</b>`;
  L.popup({{maxWidth:280}}).setLatLng([Number(p.lat), Number(p.lng)]).setContent(html).openOn(map);
  renderDetails(p);
}}
map.on('click', async e => {{
  const p = await nearestPoint(e.latlng);
  if (p) showPopup(p);
}});
document.getElementById('areaSelect').addEventListener('change', e => {{
  selectedArea = e.target.value;
  candidateLayer.redraw();
  if (fcuLayer) {{
    map.removeLayer(fcuLayer);
    fcuLayer.eachLayer(layer => {{
      if (!selectedArea || layer.feature.properties.area_col === selectedArea) layer.addTo(map);
    }});
  }}
  renderCandidates();
}});
document.getElementById('searchButton').addEventListener('click', searchId);
document.getElementById('searchBox').addEventListener('keydown', e => {{ if (e.key === 'Enter') searchId(); }});
async function searchId() {{
  const id = document.getElementById('searchBox').value.trim();
  if (!id || id.length < LOOKUP_PREFIX) return;
  const prefix = id.slice(0, LOOKUP_PREFIX).toUpperCase();
  const data = await fetchJsonMaybeGzip(`${{LOOKUP_BASE}}/${{encodeURIComponent(prefix)}}.json.gz`);
  const row = (data.p || []).find(r => String(r[0]).toUpperCase() === id.toUpperCase());
  if (!row) return alert('ID nÃ£o encontrado.');
  const tileData = await fetchJsonMaybeGzip(POINT_URL.replace('{{x}}', row[2]).replace('{{y}}', row[3]));
  const p = (tileData.p || []).find(item => String(item.id).toUpperCase() === id.toUpperCase());
  if (!p) return alert('ID encontrado, mas o tile nÃ£o carregou.');
  map.setView([p.lat, p.lng], Math.max(map.getZoom(), 15));
  showPopup(p);
}}
async function renderCandidates() {{
  const data = await topCandidatesPromise;
  const rows = selectedArea ? (data[selectedArea] || []) : Object.values(data).flat().sort((a,b) => (a.r||1e12)-(b.r||1e12)).slice(0, TOP_CANDIDATES_PER_AREA);
  document.getElementById('candidateList').innerHTML = rows.slice(0, 35).map(p => `<button class="candidate" data-id="${{esc(p.id)}}"><strong>#${{esc(p.r)}} Â· ${{pct(p.p)}}</strong><span>${{esc(p.mu || '')}}<br>${{esc(p.id)}}</span></button>`).join('') || '<p class="muted">Sem candidatos listados.</p>';
  document.querySelectorAll('.candidate').forEach(btn => btn.addEventListener('click', () => {{
    const p = rows.find(item => item.id === btn.dataset.id);
    if (p) {{ map.setView([p.lat, p.lng], Math.max(map.getZoom(), 15)); showPopup(p); }}
  }}));
}}
renderCandidates();
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera dashboard_b para usuario final.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    DASH_DIR.mkdir(parents=True, exist_ok=True)
    DATA_TILES_DIR.mkdir(parents=True, exist_ok=True)
    downloads = prepare_downloads(force=args.force)
    point_manifest = build_point_tiles(force=args.force)
    lookup_manifest = build_id_lookup(point_manifest, force=args.force)
    overview_manifest = build_overview_tiles(point_manifest, force=args.force)
    fcu_path = build_fcu_adherence(force=args.force)
    write_static_metadata(
        {
            "points": point_manifest,
            "id_lookup": lookup_manifest,
            "overview": overview_manifest,
            "fcu_adherence": str(fcu_path),
            "bounds": point_manifest.get("bounds"),
            "fcu_counts": point_manifest.get("fcu_counts", {}),
            "point_count": point_manifest.get("point_count"),
            "tile_count": point_manifest.get("tile_count"),
        },
        downloads,
    )
    html = render_source_style_html()
    html = fix_mojibake_pt(html)
    (DASH_DIR / "index.html").write_text(html, encoding="utf-8")
    log(f"[fim] dashboard_b: {DASH_DIR / 'index.html'}")
    log(f"[fim] tiles finais: {FINAL_TILE_DIR}")
    log(f"[fim] downloads: {DOWNLOAD_DIR}")


if __name__ == "__main__":
    main()

