from __future__ import annotations

import gzip
import json
import math
import shutil
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


PROJECT_DIR = Path(__file__).resolve().parents[1]
ROOT = PROJECT_DIR.parents[1]

PREDICTIONS = ROOT / "03_outputs" / "04_produtos" / "consolidado_3_modelos" / "0407_predicoes_3_modelos.geoparquet"
INPUT_PARQUET = ROOT / "01_data_input" / "0407_grade_50m_base_completa_10_areas.parquet"
FCU_GEOJSON = PROJECT_DIR / "data_tiles" / "fcu_aderencia.geojson"
RULES_JSON = PROJECT_DIR / "data_tiles" / "final" / "ranking_rules_2608.json"
SEARCH_INDEX_GZ = PROJECT_DIR / "data_tiles" / "final" / "search_index.json.gz"

MODEL_COLUMNS = {
    "completo": "prob_fcu_completo",
    "morfologico": "prob_fcu_morfologico",
    "nao_morfologico": "prob_fcu_nao_morfologico",
}


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.lower().replace("_", " ").replace("-", " ").split())


def as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clean_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else None
    if pd.isna(value):
        return None
    return value


def geometry_bounds(geometry: dict[str, Any]) -> dict[str, float] | None:
    coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if coords is None:
        return None
    xs: list[float] = []
    ys: list[float] = []

    def walk(obj: Any) -> None:
        if not isinstance(obj, list):
            return
        if len(obj) >= 2 and all(isinstance(v, (int, float)) for v in obj[:2]):
            xs.append(float(obj[0]))
            ys.append(float(obj[1]))
            return
        for item in obj:
            walk(item)

    walk(coords)
    if not xs or not ys:
        return None
    return {
        "min_lng": min(xs),
        "min_lat": min(ys),
        "max_lng": max(xs),
        "max_lat": max(ys),
    }


def merge_bounds(a: dict[str, float] | None, b: dict[str, float] | None) -> dict[str, float] | None:
    if not a:
        return b.copy() if b else None
    if not b:
        return a
    return {
        "min_lng": min(a["min_lng"], b["min_lng"]),
        "min_lat": min(a["min_lat"], b["min_lat"]),
        "max_lng": max(a["max_lng"], b["max_lng"]),
        "max_lat": max(a["max_lat"], b["max_lat"]),
    }


def load_thresholds() -> dict[str, dict[str, dict[str, float]]]:
    with RULES_JSON.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("thresholds", {}) or {}


def evidence_level(prob: Any, area_col: str, model: str, thresholds: dict[str, Any]) -> str | None:
    value = as_float(prob)
    rule = ((thresholds.get(area_col) or {}).get(model) or {})
    medium = as_float(rule.get("medium_min"))
    high = as_float(rule.get("high_min"))
    if value is None or medium is None or high is None:
        return None
    if value >= high:
        return "alto"
    if value >= medium:
        return "medio"
    return "baixo"


def update_fcu_adherence() -> dict[str, Any]:
    thresholds = load_thresholds()
    pred_cols = ["ID", "scope", "target", "prob_fcu_winner", *MODEL_COLUMNS.values()]
    id_cols = ["id", "id_fcu", "cd_fcu", "nm_fcu"]

    preds = pq.read_table(PREDICTIONS, columns=pred_cols).to_pandas()
    ids = pq.read_table(INPUT_PARQUET, columns=id_cols).to_pandas().rename(columns={"id": "ID"})
    preds["ID"] = preds["ID"].astype(str)
    ids["ID"] = ids["ID"].astype(str)

    frame = preds.merge(ids, on="ID", how="left")
    frame = frame[
        frame["target"].eq(1)
        & frame["id_fcu"].notna()
        & frame["id_fcu"].astype(str).str.strip().ne("")
    ].copy()
    frame["id_fcu"] = frame["id_fcu"].astype(str)

    for col in ["prob_fcu_winner", *MODEL_COLUMNS.values()]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["prob_fcu_max_modelos"] = frame[list(MODEL_COLUMNS.values())].max(axis=1)

    levels: dict[str, list[str | None]] = {}
    for model, col in MODEL_COLUMNS.items():
        levels[model] = [
            evidence_level(prob, area, model, thresholds)
            for prob, area in zip(frame[col], frame["scope"], strict=False)
        ]
        frame[f"nivel_{model}"] = levels[model]

    valid_cols = [f"nivel_{model}" for model in MODEL_COLUMNS]
    frame["niveis_validos"] = frame[valid_cols].notna().sum(axis=1)
    frame["niveis_baixos"] = frame[valid_cols].eq("baixo").sum(axis=1)
    frame["niveis_altos"] = frame[valid_cols].eq("alto").sum(axis=1)
    frame["celula_baixa_evidencia"] = (
        frame["niveis_validos"].eq(3)
        & frame["niveis_altos"].eq(0)
        & frame["niveis_baixos"].ge(2)
    )

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
            n_celulas=("ID", "size"),
            n_celulas_evidencia_valida=("niveis_validos", lambda s: int((s == 3).sum())),
            n_celulas_baixa_evidencia=("celula_baixa_evidencia", "sum"),
        )
        .reset_index()
    )
    stats["n_celulas_baixa_evidencia"] = stats["n_celulas_baixa_evidencia"].astype(int)
    stats["n_celulas_evidencia_valida"] = stats["n_celulas_evidencia_valida"].astype(int)
    stats["pct_celulas_baixa_evidencia"] = np.where(
        stats["n_celulas_evidencia_valida"].gt(0),
        stats["n_celulas_baixa_evidencia"] / stats["n_celulas_evidencia_valida"],
        np.nan,
    )
    stats["aderencia_modelo"] = np.select(
        [
            stats["n_celulas_evidencia_valida"].eq(0),
            stats["n_celulas_baixa_evidencia"].gt(0),
        ],
        ["sem_dado", "fcu_revisao"],
        default="fcu_mantida",
    )
    stats["regra_aderencia_modelo"] = "revisao_se_alguma_celula_tem_2_baixos_e_1_medio_ou_3_baixos"
    stats_by_id = stats.set_index("id_fcu").to_dict(orient="index")

    backup = FCU_GEOJSON.with_name(f"{FCU_GEOJSON.stem}_backup_{datetime.now():%Y%m%d_%H%M%S}.geojson")
    shutil.copy2(FCU_GEOJSON, backup)

    with FCU_GEOJSON.open("r", encoding="utf-8") as f:
        geojson = json.load(f)

    for feature in geojson.get("features", []):
        props = feature.setdefault("properties", {})
        fcu_id = str(props.get("id_fcu") or props.get("cd_fcu") or "")
        old_status = props.get("aderencia_modelo")
        row = stats_by_id.get(fcu_id)
        props["aderencia_modelo_anterior"] = old_status
        if not row:
            props["aderencia_modelo"] = "sem_dado"
            props["regra_aderencia_modelo"] = "sem_celulas_associadas_no_banco_de_predicoes"
            continue
        for key, value in row.items():
            props[key] = clean_json_value(value)

    with FCU_GEOJSON.open("w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, separators=(",", ":"))

    counts = defaultdict(int)
    for feature in geojson.get("features", []):
        counts[str((feature.get("properties") or {}).get("aderencia_modelo") or "sem_dado")] += 1
    return {"backup": str(backup), "counts": dict(counts)}


def build_search_index() -> dict[str, Any]:
    with FCU_GEOJSON.open("r", encoding="utf-8") as f:
        geojson = json.load(f)

    entries: list[dict[str, Any]] = []
    municipio: dict[tuple[str, str, str], dict[str, Any]] = {}
    area: dict[str, dict[str, Any]] = {}

    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        bounds = geometry_bounds(feature.get("geometry") or {})
        area_col = str(props.get("area_col") or "")
        area_label = str(props.get("area_label") or area_col)
        cd_mun = str(props.get("cd_mun") or "")
        nm_mun = str(props.get("nm_mun") or "")
        id_fcu = str(props.get("id_fcu") or "")
        cd_fcu = str(props.get("cd_fcu") or id_fcu)
        nm_fcu = str(props.get("nm_fcu") or cd_fcu or id_fcu)
        n_cells = clean_json_value(props.get("n_celulas"))

        fcu_term = normalize_text(
            " ".join(
                [
                    nm_fcu,
                    cd_fcu,
                    id_fcu,
                    cd_mun,
                    nm_mun,
                    area_label,
                    area_col,
                    str(props.get("tipo_fcu") or ""),
                    str(props.get("fonte_fcu") or ""),
                ]
            )
        )
        entries.append(
            {
                "type": "fcu",
                "label": nm_fcu,
                "code": cd_fcu,
                "feature_key": id_fcu or cd_fcu,
                "area_col": area_col,
                "area_label": area_label,
                "municipio": nm_mun,
                "cd_mun": cd_mun,
                "n": n_cells,
                "n_fcu": n_cells,
                "bounds": bounds,
                "term": fcu_term,
            }
        )

        mun_key = (area_col, cd_mun, nm_mun)
        mun = municipio.setdefault(
            mun_key,
            {
                "type": "municipio",
                "label": nm_mun or cd_mun,
                "code": cd_mun,
                "area_col": area_col,
                "area_label": area_label,
                "municipio": nm_mun,
                "n": 0,
                "n_fcu": 0,
                "bounds": None,
                "terms": set(),
            },
        )
        mun["n"] += 1
        mun["n_fcu"] += int(float(n_cells or 0))
        mun["bounds"] = merge_bounds(mun["bounds"], bounds)
        mun["terms"].update(normalize_text(v) for v in [nm_mun, cd_mun, area_label, area_col] if v)

        area_entry = area.setdefault(
            area_col,
            {
                "type": "area_estudo",
                "label": area_label,
                "code": area_col,
                "area_col": area_col,
                "area_label": area_label,
                "n": 0,
                "n_fcu": 0,
                "bounds": None,
                "terms": set(),
            },
        )
        area_entry["n"] += 1
        area_entry["n_fcu"] += int(float(n_cells or 0))
        area_entry["bounds"] = merge_bounds(area_entry["bounds"], bounds)
        area_entry["terms"].update(normalize_text(v) for v in [area_label, area_col] if v)

    for source in [municipio, area]:
        for item in source.values():
            terms = " ".join(sorted(t for t in item.pop("terms", set()) if t))
            item["term"] = terms
            entries.append(item)

    entries = [entry for entry in entries if entry.get("term")]
    payload = {
        "entries": entries,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "fcu_aderencia.geojson",
        "searches": ["id_celula", "nome_fcu", "codigo_fcu", "codigo_municipio", "nome_municipio", "area_estudo"],
    }
    SEARCH_INDEX_GZ.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(SEARCH_INDEX_GZ, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return {"entries": len(entries), "path": str(SEARCH_INDEX_GZ)}


def main() -> None:
    print("Atualizando regra de revisão FCU...")
    status = update_fcu_adherence()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print("Gerando índice de busca FCU/município/área...")
    index = build_search_index()
    print(json.dumps(index, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
