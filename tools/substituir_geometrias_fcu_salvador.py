"""Substitui contornos quadriculados de Salvador pelas FCUs oficiais do IBGE.

As propriedades e classificacoes do dashboard sao preservadas. FCUs
nao-setorizadas, que nao existem no arquivo agregado oficial, mantem a
geometria atual como fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import geopandas as gpd
from shapely import make_valid
from shapely.geometry import mapping


SALVADOR_AREA_COL = "area_conc_urb_salvador"


def canonical_hash(features: list[dict]) -> str:
    payload = json.dumps(
        features, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_id(value: object) -> str:
    return str(value).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("geojson", type=Path)
    parser.add_argument("fcu_oficial", type=Path)
    parser.add_argument(
        "--simplify",
        type=float,
        default=0.00002,
        help="Tolerancia em graus; mesma ordem usada no dashboard anterior.",
    )
    args = parser.parse_args()

    dashboard = json.loads(args.geojson.read_text(encoding="utf-8"))
    features = dashboard.get("features", [])
    untouched_before = [
        feature
        for feature in features
        if (feature.get("properties") or {}).get("area_col") != SALVADOR_AREA_COL
    ]
    untouched_hash = canonical_hash(untouched_before)

    official = gpd.read_file(args.fcu_oficial)
    if official.crs is None:
        raise RuntimeError("O arquivo oficial nao informa o CRS.")
    official = official.to_crs(4326)
    if "cd_fcu" not in official.columns:
        raise RuntimeError("A coluna cd_fcu nao existe no arquivo oficial.")

    official_by_id = {
        normalize_id(row.cd_fcu): row.geometry
        for row in official[["cd_fcu", "geometry"]].itertuples(index=False)
        if row.geometry is not None and not row.geometry.is_empty
    }

    replaced = 0
    fallback_ids: list[str] = []
    for feature in features:
        properties = feature.get("properties") or {}
        if properties.get("area_col") != SALVADOR_AREA_COL:
            continue
        fcu_id = normalize_id(properties.get("id_fcu") or properties.get("cd_fcu"))
        geometry = official_by_id.get(fcu_id)
        if geometry is None:
            fallback_ids.append(fcu_id)
            continue
        if not geometry.is_valid:
            geometry = make_valid(geometry)
        geometry = geometry.simplify(args.simplify, preserve_topology=True)
        if not geometry.is_valid:
            geometry = make_valid(geometry)
        feature["geometry"] = mapping(geometry)
        replaced += 1

    untouched_after = [
        feature
        for feature in features
        if (feature.get("properties") or {}).get("area_col") != SALVADOR_AREA_COL
    ]
    if canonical_hash(untouched_after) != untouched_hash:
        raise RuntimeError("A validacao detectou alteracao fora de Salvador.")

    temp_path = args.geojson.with_suffix(args.geojson.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(dashboard, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temp_path.replace(args.geojson)

    print(f"Geometrias oficiais substituidas: {replaced}")
    print(f"Fallback nao-setorizado preservado: {len(fallback_ids)}")
    print(f"Hash das demais areas preservado: {untouched_hash}")
    if fallback_ids:
        print("IDs fallback: " + ", ".join(sorted(fallback_ids)))


if __name__ == "__main__":
    main()
