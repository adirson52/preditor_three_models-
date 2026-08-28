"""Aplica a regra geral em escadas ao dashboard estatico.

O ranking geral usa ``ranking_total`` de todas as celulas da area. A FCU
original define somente o tamanho das faixas. Os tres modelos recebem as
mesmas quantidades, cada um ordenado pela sua propria probabilidade.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
POINTS_DIR = PROJECT_DIR / "data_tiles" / "final" / "points" / "12"
RULES_PATH = PROJECT_DIR / "data_tiles" / "final" / "ranking_rules_escada.json"
LEGACY_RULES_PATH = PROJECT_DIR / "data_tiles" / "final" / "ranking_rules_2608.json"
FCU_PATH = PROJECT_DIR / "data_tiles" / "fcu_aderencia.geojson"
INDEX_PATH = PROJECT_DIR / "index.html"
OUTPUT_DIR = PROJECT_DIR / "downloads"
CANONICAL_QML_PATH = (
    PROJECT_DIR / "data_tiles" / "final" / "estilos_qgis" / "estilo_revelando2608.qml"
)

SALVADOR_SOURCE = (
    PROJECT_DIR.parent
    / "05_dashboard_ebmv2_3d_evidencias_teste_2"
    / "downloads"
    / "0407_predicoes_3_modelos_salvador.gpkg"
)

MODEL_FIELDS = {
    "completo": "pc",
    "morfologico": "pm",
    "nao_morfologico": "pn",
}

QML_RANKING_MIN = 1
QML_RANKING_MAX = 104032
QML_RANKING_PALETTE = (
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
)

# Casos normativos aprovados: (F, E, prioritaria_ate, atencao_seguinte, total_destacado).
STAIR_CONTROL_POINTS = (
    (0.05, 0.05, 0.075, 0.025, 0.10),
    (0.08, 0.08, 0.12, 0.04, 0.16),
    (0.10, 0.10, 0.15, 0.05, 0.20),
    (0.12, 0.10, 0.17, 0.05, 0.22),
    (0.14, 0.11, 0.195, 0.055, 0.25),
    (0.16, 0.12, 0.22, 0.06, 0.28),
    (0.18, 0.13, 0.245, 0.065, 0.31),
    (0.21, 0.14, 0.28, 0.07, 0.35),
    (0.25, 0.15, 0.325, 0.075, 0.40),
)


def numeric(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def expansion_percent(fcu_share: float) -> float:
    """Retorna E conforme a escada aprovada, em proporcao de 0 a 1."""
    if fcu_share <= 0.10:
        return fcu_share
    if fcu_share <= 0.125:
        return 0.10
    if fcu_share <= 0.15:
        return 0.11
    if fcu_share <= 0.175:
        return 0.12
    if fcu_share <= 0.20:
        return 0.13
    if fcu_share <= 0.225:
        return 0.14
    return 0.15


def validate_stair_control_points() -> None:
    """Impede alterações futuras que quebrem a tabela normativa da escada."""
    for fcu_share, expected_e, expected_priority, expected_attention, expected_total in STAIR_CONTROL_POINTS:
        expansion = expansion_percent(fcu_share)
        actual = (expansion, fcu_share + expansion / 2, expansion / 2, fcu_share + expansion)
        expected = (expected_e, expected_priority, expected_attention, expected_total)
        if any(not math.isclose(value, target, abs_tol=1e-12) for value, target in zip(actual, expected)):
            raise AssertionError(f"Escada invalida para F={fcu_share:.1%}: {actual} != {expected}")


def iter_tile_points() -> Any:
    for path in sorted(POINTS_DIR.rglob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
        for point in payload.get("p", []):
            yield point


def build_database(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("PRAGMA temp_store=FILE")
    connection.execute(
        """
        CREATE TABLE points (
          id TEXT NOT NULL,
          area TEXT NOT NULL,
          target INTEGER NOT NULL,
          rank_general INTEGER,
          completo REAL,
          morfologico REAL,
          nao_morfologico REAL,
          lat REAL,
          lng REAL,
          PRIMARY KEY (area, id)
        ) WITHOUT ROWID
        """
    )
    insert = "INSERT OR REPLACE INTO points VALUES (?,?,?,?,?,?,?,?,?)"
    batch: list[tuple[Any, ...]] = []
    total = 0
    for point in iter_tile_points():
        area = str(point.get("a") or "")
        point_id = str(point.get("id") or "")
        if not area or not point_id:
            continue
        batch.append(
            (
                point_id,
                area,
                int(numeric(point.get("t")) or 0),
                int(numeric(point.get("rt")) or 0) or None,
                numeric(point.get("pc")),
                numeric(point.get("pm")),
                numeric(point.get("pn")),
                numeric(point.get("lat")),
                numeric(point.get("lng")),
            )
        )
        if len(batch) >= 25_000:
            connection.executemany(insert, batch)
            total += len(batch)
            batch.clear()
            print(f"pontos indexados: {total:,}", flush=True)
    if batch:
        connection.executemany(insert, batch)
        total += len(batch)
    connection.commit()
    print(f"total de pontos indexados: {total:,}", flush=True)
    connection.execute("CREATE INDEX points_area_target ON points(area, target)")
    for model in MODEL_FIELDS:
        connection.execute(
            f"CREATE INDEX points_area_{model} ON points(area, {model} DESC, id ASC)"
        )
    connection.commit()
    return connection


def boundary_at(
    connection: sqlite3.Connection,
    area: str,
    field: str,
    position: int,
) -> dict[str, Any] | None:
    if position <= 0:
        return None
    row = connection.execute(
        f"""
        SELECT {field}, id
        FROM points
        WHERE area = ? AND {field} IS NOT NULL
        ORDER BY {field} DESC, id ASC
        LIMIT 1 OFFSET ?
        """,
        (area, position - 1),
    ).fetchone()
    if not row:
        return None
    return {"score": round(float(row[0]), 6), "last_id": str(row[1])}


def build_rules(connection: sqlite3.Connection) -> dict[str, Any]:
    rules: dict[str, Any] = {}
    thresholds: dict[str, Any] = {}
    rows = connection.execute(
        """
        SELECT area, COUNT(*) AS total, SUM(CASE WHEN target = 1 THEN 1 ELSE 0 END) AS n_fcu
        FROM points GROUP BY area ORDER BY area
        """
    ).fetchall()
    for area, total_raw, n_fcu_raw in rows:
        total = int(total_raw)
        n_fcu = int(n_fcu_raw or 0)
        fcu_share = n_fcu / total if total else 0.0
        expansion = min(expansion_percent(fcu_share), max(0.0, 1.0 - fcu_share))
        expansion_count = min(total - n_fcu, round_half_up(expansion * total))
        priority_extra = (expansion_count + 1) // 2
        attention_count = expansion_count - priority_extra
        priority_limit = n_fcu + priority_extra
        attention_limit = priority_limit + attention_count
        rules[area] = {
            "total": total,
            "n_fcu": n_fcu,
            "p_fcu": round(fcu_share, 6),
            "expansion_pct": round(expansion, 6),
            "expansion_count": expansion_count,
            "priority_extra": priority_extra,
            "priority_limit": priority_limit,
            "attention_count": attention_count,
            "attention_limit": attention_limit,
            "other_count": total - attention_limit,
            "ranking_universe": "todas_as_celulas_da_area",
            "ranking_field": "ranking_total",
        }
        thresholds[area] = {}
        for model in MODEL_FIELDS:
            high = boundary_at(connection, area, model, priority_limit)
            medium = boundary_at(connection, area, model, attention_limit)
            thresholds[area][model] = {
                "high_min": high["score"] if high else None,
                "high_last_id": high["last_id"] if high else None,
                "medium_min": medium["score"] if medium else None,
                "medium_last_id": medium["last_id"] if medium else None,
                "high_count": priority_limit,
                "medium_count": attention_count,
                "low_count": total - attention_limit,
                "n": total,
            }
        print(
            f"{area}: FCU={fcu_share:.2%}, E={expansion:.2%}, "
            f"prioritaria={priority_limit:,}, atencao={attention_count:,}",
            flush=True,
        )
    payload = {
        "version": 2,
        "method": "escada_fcu_ranking_geral",
        "formula": {
            "priority_limit": "n_fcu + ceil(expansion_count / 2)",
            "attention_limit": "n_fcu + expansion_count",
            "classification": "ranking_total de todas as celulas",
        },
        "steps": [
            {"fcu_max": 0.10, "expansion": "igual_ao_percentual_fcu"},
            {"fcu_min_exclusive": 0.10, "fcu_max": 0.125, "expansion": 0.10},
            {"fcu_min_exclusive": 0.125, "fcu_max": 0.15, "expansion": 0.11},
            {"fcu_min_exclusive": 0.15, "fcu_max": 0.175, "expansion": 0.12},
            {"fcu_min_exclusive": 0.175, "fcu_max": 0.20, "expansion": 0.13},
            {"fcu_min_exclusive": 0.20, "fcu_max": 0.225, "expansion": 0.14},
            {"fcu_min_exclusive": 0.225, "expansion": 0.15},
        ],
        "rules": rules,
        "thresholds": thresholds,
    }
    RULES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LEGACY_RULES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def evidence_level(
    score: Any,
    point_id: str,
    rule: dict[str, Any],
) -> str | None:
    value = numeric(score)
    if value is None:
        return None

    def within(boundary_name: str) -> bool:
        threshold = numeric(rule.get(f"{boundary_name}_min"))
        last_id = str(rule.get(f"{boundary_name}_last_id") or "")
        if threshold is None:
            return False
        if value > threshold:
            return True
        return math.isclose(value, threshold, rel_tol=0, abs_tol=5e-7) and point_id <= last_id

    if within("high"):
        return "alto"
    if within("medium"):
        return "medio"
    return "baixo"


def update_fcu_types(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, int]:
    backup = FCU_PATH.with_name(f"{FCU_PATH.stem}_antes_escada.geojson")
    if not backup.exists():
        shutil.copy2(FCU_PATH, backup)
    fcu = gpd.read_file(FCU_PATH).to_crs(4674)
    if "area_col" not in fcu.columns:
        raise RuntimeError("FCU GeoJSON sem area_col")
    fcu["__feature_index"] = np.arange(len(fcu), dtype=int)
    counts = {"fcu_mantida": 0, "fcu_revisao": 0, "sem_dado": 0}

    for area in sorted(fcu["area_col"].dropna().astype(str).unique()):
        area_fcu = fcu.loc[fcu["area_col"].astype(str).eq(area)].copy()
        rows = connection.execute(
            """
            SELECT id, completo, morfologico, nao_morfologico, lng, lat
            FROM points WHERE area = ? AND target = 1 AND lng IS NOT NULL AND lat IS NOT NULL
            """,
            (area,),
        ).fetchall()
        if not rows or area_fcu.empty:
            continue
        points = pd.DataFrame(
            rows,
            columns=["id", "completo", "morfologico", "nao_morfologico", "lng", "lat"],
        )
        geo_points = gpd.GeoDataFrame(
            points,
            geometry=gpd.points_from_xy(points["lng"], points["lat"]),
            crs=4674,
        )
        joined = gpd.sjoin(
            geo_points,
            area_fcu[["__feature_index", "geometry"]],
            how="left",
            predicate="within",
        )
        model_rules = payload["thresholds"].get(area, {})
        for model in MODEL_FIELDS:
            joined[f"nivel_{model}"] = [
                evidence_level(score, str(point_id), model_rules.get(model, {}))
                for score, point_id in zip(joined[model], joined["id"], strict=False)
            ]
        level_cols = [f"nivel_{model}" for model in MODEL_FIELDS]
        joined["valid"] = joined[level_cols].notna().sum(axis=1).eq(3)
        joined["low_count"] = joined[level_cols].eq("baixo").sum(axis=1)
        joined["high_count"] = joined[level_cols].eq("alto").sum(axis=1)
        joined["low_evidence"] = joined["valid"] & joined["high_count"].eq(0) & joined["low_count"].ge(2)
        stats = joined.dropna(subset=["__feature_index"]).groupby("__feature_index").agg(
            n_celulas=("id", "size"),
            n_celulas_evidencia_valida=("valid", "sum"),
            n_celulas_baixa_evidencia=("low_evidence", "sum"),
        )
        for feature_index, row in stats.iterrows():
            valid = int(row["n_celulas_evidencia_valida"])
            low = int(row["n_celulas_baixa_evidencia"])
            pct = low / valid if valid else math.nan
            status = "sem_dado" if valid == 0 else ("fcu_revisao" if pct >= 0.50 else "fcu_mantida")
            mask = fcu["__feature_index"].eq(int(feature_index))
            fcu.loc[mask, "n_celulas"] = int(row["n_celulas"])
            fcu.loc[mask, "n_celulas_evidencia_valida"] = valid
            fcu.loc[mask, "n_celulas_baixa_evidencia"] = low
            fcu.loc[mask, "pct_celulas_baixa_evidencia"] = pct
            fcu.loc[mask, "aderencia_modelo"] = status
            fcu.loc[mask, "regra_aderencia_modelo"] = "tipo_2_se_50pct_ou_mais_tem_3_baixos_ou_2_baixos_e_1_medio"

    fcu["aderencia_modelo"] = fcu["aderencia_modelo"].fillna("sem_dado")
    fcu = fcu.drop(columns=["__feature_index"])
    fcu.to_file(FCU_PATH, driver="GeoJSON")
    for value, count in fcu["aderencia_modelo"].value_counts().items():
        counts[str(value)] = int(count)
    return counts


def patch_dashboard(payload: dict[str, Any]) -> None:
    html = INDEX_PATH.read_text(encoding="utf-8")
    rules = {
        area: {
            key: value
            for key, value in rule.items()
            if key not in {"ranking_universe", "ranking_field"}
        }
        for area, rule in payload["rules"].items()
    }
    thresholds = {
        area: {
            model: {
                key: value
                for key, value in rule.items()
                if key in {"high_min", "high_last_id", "medium_min", "medium_last_id", "high_count", "medium_count", "low_count"}
            }
            for model, rule in models.items()
        }
        for area, models in payload["thresholds"].items()
    }
    html, count_rules = re.subn(
        r"const AREA_RANK_RULES = \{.*?\};",
        "const AREA_RANK_RULES = " + json.dumps(rules, ensure_ascii=False, separators=(",", ":")) + ";",
        html,
        count=1,
    )
    html, count_thresholds = re.subn(
        r"const MODEL_EVIDENCE_THRESHOLDS = \{.*?\};",
        "const MODEL_EVIDENCE_THRESHOLDS = " + json.dumps(thresholds, ensure_ascii=False, separators=(",", ":")) + ";",
        html,
        count=1,
    )
    if count_rules != 1 or count_thresholds != 1:
        raise RuntimeError("Nao foi possivel atualizar as regras embutidas no index.html")
    INDEX_PATH.write_text(html, encoding="utf-8")


def qml_action() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<qgis version=\"3.34\" styleCategories=\"Symbology|Labeling\">
  <renderer-v2 type=\"categorizedSymbol\" attr=\"classe_acao\">
    <categories>
      <category value=\"atencao_prioritaria\" label=\"Atenção prioritária\" symbol=\"0\"/>
      <category value=\"atencao\" label=\"Atenção\" symbol=\"1\"/>
      <category value=\"demais_areas\" label=\"Demais áreas\" symbol=\"2\"/>
      <category value=\"sem_resultado\" label=\"Sem resultado\" symbol=\"3\"/>
    </categories>
    <symbols>
      <symbol name=\"0\" type=\"marker\"><layer class=\"SimpleMarker\"><Option name=\"name\" value=\"circle\"/><Option name=\"color\" value=\"215,25,28,235\"/><Option name=\"outline_color\" value=\"153,27,27,255\"/><Option name=\"outline_width\" value=\"0.2\"/><Option name=\"size\" value=\"2.2\"/><Option name=\"size_unit\" value=\"MM\"/></layer></symbol>
      <symbol name=\"1\" type=\"marker\"><layer class=\"SimpleMarker\"><Option name=\"name\" value=\"circle\"/><Option name=\"color\" value=\"242,142,43,225\"/><Option name=\"outline_color\" value=\"180,83,9,255\"/><Option name=\"outline_width\" value=\"0.2\"/><Option name=\"size\" value=\"2.2\"/><Option name=\"size_unit\" value=\"MM\"/></layer></symbol>
      <symbol name=\"2\" type=\"marker\"><layer class=\"SimpleMarker\"><Option name=\"name\" value=\"circle\"/><Option name=\"color\" value=\"0,0,0,0\"/><Option name=\"outline_color\" value=\"0,0,0,0\"/><Option name=\"size\" value=\"2.2\"/><Option name=\"size_unit\" value=\"MM\"/></layer></symbol>
      <symbol name=\"3\" type=\"marker\"><layer class=\"SimpleMarker\"><Option name=\"name\" value=\"circle\"/><Option name=\"color\" value=\"0,0,0,0\"/><Option name=\"outline_color\" value=\"0,0,0,0\"/><Option name=\"size\" value=\"2.2\"/><Option name=\"size_unit\" value=\"MM\"/></layer></symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""


def qml_fcu() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<qgis version=\"3.34\" styleCategories=\"Symbology|Labeling\">
  <renderer-v2 type=\"categorizedSymbol\" attr=\"fcu_tipo\">
    <categories>
      <category value=\"FCU tipo 1\" label=\"FCU tipo 1\" symbol=\"0\"/>
      <category value=\"FCU tipo 2\" label=\"FCU tipo 2\" symbol=\"1\"/>
    </categories>
    <symbols>
      <symbol name=\"0\" type=\"fill\"><layer class=\"SimpleFill\"><Option name=\"color\" value=\"55,65,81,45\"/><Option name=\"outline_color\" value=\"31,41,55,235\"/><Option name=\"outline_width\" value=\"0.7\"/><Option name=\"outline_width_unit\" value=\"MM\"/></layer></symbol>
      <symbol name=\"1\" type=\"fill\"><layer class=\"SimpleFill\"><Option name=\"color\" value=\"203,213,225,52\"/><Option name=\"outline_color\" value=\"100,116,139,235\"/><Option name=\"outline_style\" value=\"dash\"/><Option name=\"outline_width\" value=\"0.7\"/><Option name=\"outline_width_unit\" value=\"MM\"/></layer></symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""


def qml_ranking_old() -> str:
    """Reproduz a rampa antiga: ranking_total 1..104032, vermelho ate azul."""
    span = QML_RANKING_MAX - QML_RANKING_MIN
    width = span / len(QML_RANKING_PALETTE)
    ranges: list[str] = []
    symbols: list[str] = []
    for index, (red, green, blue) in enumerate(QML_RANKING_PALETTE):
        lower = QML_RANKING_MIN + index * width
        upper = 999999999 if index == len(QML_RANKING_PALETTE) - 1 else QML_RANKING_MIN + (index + 1) * width
        label_upper = QML_RANKING_MAX if index == len(QML_RANKING_PALETTE) - 1 else upper
        alpha = 255
        ranges.append(
            f'      <range lower="{lower:.6f}" upper="{upper:.6f}" symbol="{index}" '
            f'label="{lower:.0f} - {label_upper:.0f}" render="true"/>'
        )
        symbols.append(
            f'      <symbol name="{index}" type="marker"><layer class="SimpleMarker">'
            f'<Option name="name" value="circle"/><Option name="color" value="{red},{green},{blue},{alpha}"/>'
            f'<Option name="outline_color" value="{red},{green},{blue},{alpha}"/>'
            '<Option name="outline_width" value="0"/><Option name="size" value="2.2"/>'
            '<Option name="size_unit" value="MM"/></layer></symbol>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<qgis version="3.34" styleCategories="Symbology|Labeling">\n'
        '  <renderer-v2 type="graduatedSymbol" attr="ranking_total" graduatedMethod="GraduatedColor">\n'
        '    <ranges>\n' + "\n".join(ranges) + '\n    </ranges>\n'
        '    <symbols>\n' + "\n".join(symbols) + '\n    </symbols>\n'
        '  </renderer-v2>\n</qgis>\n'
    )


def write_qml_files() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    public_styles = RULES_PATH.parent / "estilos_qgis"
    public_styles.mkdir(parents=True, exist_ok=True)
    ranking_qml = (
        CANONICAL_QML_PATH.read_text(encoding="utf-8")
        if CANONICAL_QML_PATH.exists()
        else qml_ranking_old()
    )
    for folder in (OUTPUT_DIR, public_styles):
        (folder / "estilo_revelando2608.qml").write_text(ranking_qml, encoding="utf-8")
        (folder / "estilo_ranking_total_qml_antigo.qml").write_text(ranking_qml, encoding="utf-8")
        (folder / "estilo_celulas_acao_escada.qml").write_text(qml_action(), encoding="utf-8")
        (folder / "estilo_fcu_tipos_transparente.qml").write_text(qml_fcu(), encoding="utf-8")


def class_from_rank(rank: Any, rule: dict[str, Any]) -> str:
    value = numeric(rank)
    if value is None or value <= 0:
        return "sem_resultado"
    if value <= int(rule["priority_limit"]):
        return "atencao_prioritaria"
    if value <= int(rule["attention_limit"]):
        return "atencao"
    return "demais_areas"


def level_from_rank(rank: Any, rule: dict[str, Any]) -> str:
    value = numeric(rank)
    if value is None or value <= 0:
        return "sem_dado"
    if value <= int(rule["priority_limit"]):
        return "alto"
    if value <= int(rule["attention_limit"]):
        return "medio"
    return "baixo"


def build_salvador_gpkg(payload: dict[str, Any]) -> Path | None:
    if not SALVADOR_SOURCE.exists():
        print(f"GPKG Salvador nao encontrado: {SALVADOR_SOURCE}")
        return None
    area = "area_conc_urb_salvador"
    rule = payload["rules"][area]
    columns = [
        "ID", "scope", "Polo", "target", "id_col", "id_row",
        "id_rg2017_cd_mun", "id_rg2017_mun_nome", "id_ibge_cd_setor",
        "prob_fcu_completo", "ranking_total_completo",
        "prob_fcu_morfologico", "ranking_total_morfologico",
        "prob_fcu_nao_morfologico", "ranking_total_nao_morfologico",
        "winner_scenario", "prob_fcu_winner", "ranking_total_winner", "geometry",
    ]
    cells = gpd.read_file(SALVADOR_SOURCE, layer="predicoes_base0407", columns=columns)
    cells["ranking_geral"] = pd.to_numeric(cells["ranking_total_winner"], errors="coerce").astype("Int64")
    cells["ranking_total"] = cells["ranking_geral"]
    cells["classe_acao"] = [class_from_rank(value, rule) for value in cells["ranking_geral"]]
    cells["nivel_completo"] = [level_from_rank(value, rule) for value in cells["ranking_total_completo"]]
    cells["nivel_morfologico"] = [level_from_rank(value, rule) for value in cells["ranking_total_morfologico"]]
    cells["nivel_ibge"] = [level_from_rank(value, rule) for value in cells["ranking_total_nao_morfologico"]]
    cells["situacao_territorial"] = np.where(cells["target"].eq(1), "FCU original", "fora da FCU original")

    fcu = gpd.read_file(FCU_PATH).to_crs(cells.crs)
    fcu = fcu.loc[fcu["area_col"].astype(str).eq(area)].copy()
    fcu["fcu_tipo"] = np.select(
        [fcu["aderencia_modelo"].eq("fcu_revisao"), fcu["aderencia_modelo"].eq("fcu_mantida")],
        ["FCU tipo 2", "FCU tipo 1"],
        default="sem dado",
    )
    centroids = cells.to_crs(3857).geometry.centroid.to_crs(cells.crs)
    point_cells = gpd.GeoDataFrame(
        cells[["ID"]].copy(), geometry=centroids, crs=cells.crs
    )
    joined = gpd.sjoin(
        point_cells,
        fcu[["id_fcu", "fcu_tipo", "geometry"]],
        how="left",
        predicate="within",
    ).drop_duplicates(subset=["ID"])
    missing_ids = joined.loc[joined["fcu_tipo"].isna() & joined["ID"].isin(cells.loc[cells["target"].eq(1), "ID"]), "ID"]
    if not missing_ids.empty:
        nearest_points = point_cells.loc[point_cells["ID"].isin(missing_ids)].to_crs(3857)
        nearest_fcu = fcu[["id_fcu", "fcu_tipo", "geometry"]].to_crs(3857)
        nearest = gpd.sjoin_nearest(
            nearest_points,
            nearest_fcu,
            how="left",
            max_distance=80,
        ).drop_duplicates(subset=["ID"])
        nearest_values = nearest.set_index("ID")[["id_fcu", "fcu_tipo"]]
        joined = joined.set_index("ID")
        joined.update(nearest_values)
        joined = joined.reset_index()
    membership = joined.set_index("ID")[["id_fcu", "fcu_tipo"]]
    cells = cells.join(membership, on="ID")
    cells.loc[cells["target"].ne(1), ["id_fcu", "fcu_tipo"]] = [None, None]
    cells["fcu_tipo"] = cells["fcu_tipo"].fillna("fora da FCU original")
    cells["situacao_territorial"] = cells["fcu_tipo"]
    cells["nivel_ibge_espectral"] = cells["nivel_ibge"]

    output = OUTPUT_DIR / "preditor_fcu_salvador_ranking_escada.gpkg"
    if output.exists():
        output.unlink()
    cells.to_file(output, layer="celulas_acao", driver="GPKG")
    fcu.to_file(output, layer="fcu_tipos", driver="GPKG")
    summary = pd.DataFrame([{"area": area, **rule}])
    with sqlite3.connect(output) as connection:
        summary.to_sql("resumo_area", connection, if_exists="replace", index=False)
        pd.DataFrame(payload["steps"]).to_sql("regra_escada", connection, if_exists="replace", index=False)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-gpkg", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_stair_control_points()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="preditor_escada_") as temp:
        connection = build_database(Path(temp) / "points.sqlite")
        payload = build_rules(connection)
        counts = update_fcu_types(connection, payload)
        print("FCUs:", counts)
        connection.close()
    patch_dashboard(payload)
    write_qml_files()
    gpkg = None if args.skip_gpkg else build_salvador_gpkg(payload)
    print(f"regras: {RULES_PATH}")
    print(f"QML: {OUTPUT_DIR}")
    if gpkg:
        print(f"GPKG: {gpkg}")


if __name__ == "__main__":
    main()
