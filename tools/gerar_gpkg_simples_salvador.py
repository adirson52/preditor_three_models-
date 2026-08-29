"""Gera uma saida leve de pontos com o resultado final de Salvador."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio


LAYER_NAME = "salvador_saida"
SOURCE_LAYER = "celulas_acao"
OUTPUT_FIELDS = [
    "id_celula",
    "cod_municipio",
    "municipio",
    "longitude",
    "latitude",
    "probabilidade_final",
    "ranking_final",
    "classe_acao",
    "situacao_fcu",
    "modelo_final",
]

MUNICIPIOS = {
    "2905701": "Camaçari",
    "2906501": "Candeias",
    "2910057": "Dias d'Ávila",
    "2919207": "Lauro de Freitas",
    "2919926": "Madre de Deus",
    "2921005": "Mata de São João",
    "2927408": "Salvador",
    "2929206": "São Francisco do Conde",
    "2929503": "São Sebastião do Passé",
    "2930709": "Simões Filho",
}

CLASSES = {
    "atencao_prioritaria": "atenção prioritária",
    "atencao": "atenção",
    "demais_areas": "demais áreas",
}

MODELOS = {
    "completo": "Completo",
    "morfologico": "Morfológico",
    "nao_morfologico": "IBGE",
}


def parse_args() -> argparse.Namespace:
    dashboard_root = Path(__file__).resolve().parents[1]
    outputs_root = dashboard_root.parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=dashboard_root / "downloads" / "preditor_fcu_salvador_ranking_escada.gpkg",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=outputs_root / "07_entrega_final" / "preditor_fcu_salvador_saida_simples.gpkg",
    )
    return parser.parse_args()


def normalize_code(values: pd.Series) -> pd.Series:
    return values.astype("string").str.replace(r"\.0$", "", regex=True)


def validate_source(cells: gpd.GeoDataFrame) -> None:
    if cells.empty:
        raise ValueError("A camada de origem esta vazia.")
    if cells.crs is None:
        raise ValueError("A camada de origem nao possui CRS.")
    if cells["ID"].isna().any() or not cells["ID"].is_unique:
        raise ValueError("ID de celula ausente ou duplicado.")
    required = ["prob_fcu_winner", "ranking_total", "classe_acao", "situacao_territorial"]
    if cells[required].isna().any().any():
        raise ValueError("Ha valores nulos nos campos finais.")


def build_output(cells: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    # Salvador esta no fuso UTM 23S. O centroide e calculado em metros e
    # devolvido ao CRS geografico oficial da fonte (SIRGAS 2000 / EPSG:4674).
    points = cells.to_crs(31983).geometry.centroid.to_crs(cells.crs)
    codes = normalize_code(cells["id_rg2017_cd_mun"])
    source_names = cells["id_rg2017_mun_nome"].astype("string")
    names = codes.map(MUNICIPIOS).fillna(source_names)

    result = gpd.GeoDataFrame(
        {
            "id_celula": cells["ID"].astype("string"),
            "cod_municipio": codes,
            "municipio": names,
            "longitude": points.x.astype("float64"),
            "latitude": points.y.astype("float64"),
            "probabilidade_final": pd.to_numeric(cells["prob_fcu_winner"], errors="raise").astype("float64"),
            "ranking_final": pd.to_numeric(cells["ranking_total"], errors="raise").astype("int64"),
            "classe_acao": cells["classe_acao"].map(CLASSES).fillna(cells["classe_acao"]).astype("string"),
            "situacao_fcu": cells["situacao_territorial"].astype("string"),
            "modelo_final": cells["winner_scenario"].map(MODELOS).fillna(cells["winner_scenario"]).astype("string"),
        },
        geometry=points,
        crs=cells.crs,
    )
    return result[[*OUTPUT_FIELDS, "geometry"]]


def validate_file(path: Path, expected_count: int) -> dict[str, object]:
    info = pyogrio.read_info(path, layer=LAYER_NAME)
    with sqlite3.connect(path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        row = connection.execute(
            f'SELECT COUNT(*), COUNT(DISTINCT id_celula), MIN(ranking_final), '
            f'MAX(ranking_final), MIN(probabilidade_final), MAX(probabilidade_final) FROM "{LAYER_NAME}"'
        ).fetchone()
        classes = dict(
            connection.execute(
                f'SELECT classe_acao, COUNT(*) FROM "{LAYER_NAME}" GROUP BY classe_acao ORDER BY classe_acao'
            ).fetchall()
        )
    if integrity != "ok":
        raise ValueError(f"GeoPackage invalido: {integrity}")
    if info["geometry_type"] != "Point":
        raise ValueError(f"Geometria inesperada: {info['geometry_type']}")
    if int(info["features"]) != expected_count or row[0] != expected_count or row[1] != expected_count:
        raise ValueError("A contagem gravada nao corresponde a origem.")
    if row[2] != 1 or row[3] != expected_count:
        raise ValueError("O ranking final nao cobre o intervalo esperado.")
    return {
        "arquivo": str(path),
        "camada": LAYER_NAME,
        "crs": info["crs"],
        "geometria": info["geometry_type"],
        "celulas": row[0],
        "ids_unicos": row[1],
        "ranking_min": row[2],
        "ranking_max": row[3],
        "probabilidade_min": row[4],
        "probabilidade_max": row[5],
        "classes": classes,
        "campos": OUTPUT_FIELDS,
        "tamanho_bytes": path.stat().st_size,
        "integridade": integrity,
    }


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    output.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "ID",
        "id_rg2017_cd_mun",
        "id_rg2017_mun_nome",
        "prob_fcu_winner",
        "ranking_total",
        "classe_acao",
        "situacao_territorial",
        "winner_scenario",
        "geometry",
    ]
    cells = gpd.read_file(source, layer=SOURCE_LAYER, columns=columns, engine="pyogrio")
    validate_source(cells)
    result = build_output(cells)

    if output.exists():
        output.unlink()
    pyogrio.write_dataframe(
        result,
        output,
        layer=LAYER_NAME,
        driver="GPKG",
        layer_options={"SPATIAL_INDEX": "YES"},
    )
    with sqlite3.connect(output) as connection:
        connection.execute(
            f'CREATE UNIQUE INDEX "idx_{LAYER_NAME}_id" ON "{LAYER_NAME}" (id_celula)'
        )
        connection.execute(
            f'CREATE INDEX "idx_{LAYER_NAME}_ranking" ON "{LAYER_NAME}" (ranking_final)'
        )

    summary = validate_file(output, len(result))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
