"""Monta o pacote QGIS de Salvador com os tres estilos usados no site."""

from __future__ import annotations

import json
import shutil
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pyogrio


def dashboard_paths() -> dict[str, Path]:
    dashboard = Path(__file__).resolve().parents[1]
    outputs = dashboard.parent
    delivery = outputs / "07_entrega_final"
    return {
        "simple": delivery / "preditor_fcu_salvador_saida_simples.gpkg",
        "full": dashboard / "downloads" / "preditor_fcu_salvador_ranking_escada.gpkg",
        "ranking_source": dashboard
        / "data_tiles"
        / "final"
        / "estilos_qgis"
        / "por_area"
        / "estilo_revelando2608_area_conc_urb_salvador.qml",
        "fcu_source": dashboard / "downloads" / "estilo_fcu_tipos_transparente.qml",
        "folder": delivery / "QGIS_Salvador_Visualizacao",
        "zip": delivery / "preditor_fcu_salvador_qgis.zip",
    }


def option_value(symbol: ET.Element, name: str) -> str:
    for option in symbol.findall(".//Option"):
        if option.get("name") == name:
            return option.get("value", "")
    raise ValueError(f"Opcao {name!r} ausente no simbolo {symbol.get('name')}")


def simple_marker_symbol(name: str, color: str, size: str = "1.8") -> ET.Element:
    symbol = ET.Element("symbol", {"name": name, "type": "marker", "alpha": "1"})
    layer = ET.SubElement(symbol, "layer", {"class": "SimpleMarker", "enabled": "1", "locked": "0"})
    values = {
        "name": "circle",
        "color": color,
        "outline_color": "35,35,35,0",
        "outline_style": "solid",
        "outline_width": "0",
        "outline_width_unit": "MM",
        "size": size,
        "size_unit": "MM",
    }
    for key, value in values.items():
        ET.SubElement(layer, "Option", {"name": key, "value": value})
    return symbol


def generate_ranking_qml(source: Path, destination: Path) -> dict[str, object]:
    source_root = ET.parse(source).getroot()
    source_renderer = source_root.find("renderer-v2")
    if source_renderer is None:
        raise ValueError("Renderer de ranking ausente.")
    ranges = source_renderer.find("ranges")
    symbols = source_renderer.find("symbols")
    if ranges is None or symbols is None:
        raise ValueError("Faixas ou simbolos de ranking ausentes.")
    source_symbols = {symbol.get("name", ""): symbol for symbol in symbols.findall("symbol")}

    root = ET.Element(
        "qgis",
        {"version": "3.40.5-Bratislava", "styleCategories": "Symbology|Labeling"},
    )
    renderer = ET.SubElement(
        root,
        "renderer-v2",
        {
            "type": "graduatedSymbol",
            "attr": "ranking_final",
            "graduatedMethod": "GraduatedColor",
            "symbollevels": "0",
            "forceraster": "0",
            "enableorderby": "0",
        },
    )
    output_ranges = ET.SubElement(renderer, "ranges")
    for rank_range in ranges.findall("range"):
        ET.SubElement(output_ranges, "range", dict(rank_range.attrib))

    output_symbols = ET.SubElement(renderer, "symbols")
    colors: list[str] = []
    for number in range(50):
        name = str(number)
        color = option_value(source_symbols[name], "color")
        colors.append(color.split(",rgb:", 1)[0])
        output_symbols.append(simple_marker_symbol(name, color))

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
    first = output_ranges.findall("range")[0]
    last = output_ranges.findall("range")[-1]
    return {
        "campo": "ranking_final",
        "faixas": len(output_ranges.findall("range")),
        "simbolos": len(output_symbols.findall("symbol")),
        "limite_inicial": first.get("lower"),
        "limite_final": last.get("upper"),
        "cores": colors,
    }


def generate_action_qml(destination: Path) -> None:
    root = ET.Element(
        "qgis",
        {"version": "3.40.5-Bratislava", "styleCategories": "Symbology|Labeling"},
    )
    renderer = ET.SubElement(root, "renderer-v2", {"type": "categorizedSymbol", "attr": "classe_acao"})
    categories = ET.SubElement(renderer, "categories")
    definitions = [
        ("atenção prioritária", "Atenção prioritária", "240,59,32,235", "0"),
        ("atenção", "Atenção", "242,142,43,225", "1"),
        ("demais áreas", "Demais áreas", "0,0,0,0", "2"),
    ]
    for value, label, _color, symbol_name in definitions:
        ET.SubElement(
            categories,
            "category",
            {"value": value, "label": label, "symbol": symbol_name, "render": "true"},
        )
    symbols = ET.SubElement(renderer, "symbols")
    for _value, _label, color, symbol_name in definitions:
        symbols.append(simple_marker_symbol(symbol_name, color, size="2.2"))
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)


def write_readme(path: Path) -> None:
    path.write_text(
        """PACOTE QGIS — SALVADOR

Arquivo de dados: preditor_fcu_salvador_qgis.gpkg
CRS: SIRGAS 2000 / EPSG:4674

CAMADAS
- salvador_saida: pontos das 225.164 celulas, com probabilidade e ranking finais.
- fcu_tipos: poligonos continuos das FCUs originais.

COMO REPRODUZIR A LEGENDA DO SITE
1. Adicione salvador_saida duas vezes ao projeto.
2. Na primeira copia, escolha Propriedades > Simbologia > Estilo > Carregar estilo:
   01_ranking_qml_salvador.qml
   Renomeie a camada para Ranking QML.
3. Na segunda copia, carregue:
   02_prioridade_modelo.qml
   Renomeie a camada para Prioridade do modelo.
4. Na camada fcu_tipos, carregue:
   03_fcu_tipos.qml
   Renomeie a camada para FCU.

LEITURA
- Ranking QML: 50 cores calculadas para o ranking local de Salvador.
- Atenção prioritária: vermelho.
- Atenção: laranja.
- Demais áreas: transparente, mas as feicoes continuam consultaveis.
- FCU tipo 1: cinza escuro transparente.
- FCU tipo 2: cinza claro transparente e contorno tracejado.

ABERTURA SUGERIDA
- Deixe apenas Ranking QML visivel na primeira abertura.
- Ative Prioridade do modelo e FCU quando quiser comparar as classificacoes.
- O ranking 1 representa a celula de maior prioridade.
""",
        encoding="utf-8",
    )


def validate_package(gpkg: Path, ranking_qml: Path, action_qml: Path, fcu_qml: Path) -> dict[str, object]:
    layers = {name: geometry for name, geometry in pyogrio.list_layers(gpkg).tolist()}
    if layers != {"salvador_saida": "Point", "fcu_tipos": "MultiPolygon"}:
        raise ValueError(f"Camadas inesperadas: {layers}")
    point_info = pyogrio.read_info(gpkg, layer="salvador_saida")
    fcu_info = pyogrio.read_info(gpkg, layer="fcu_tipos")
    for qml in (ranking_qml, action_qml, fcu_qml):
        ET.parse(qml)
    with sqlite3.connect(gpkg) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise ValueError(f"GeoPackage invalido: {integrity}")
    ranking_renderer = ET.parse(ranking_qml).getroot().find("renderer-v2")
    action_renderer = ET.parse(action_qml).getroot().find("renderer-v2")
    fcu_renderer = ET.parse(fcu_qml).getroot().find("renderer-v2")
    return {
        "gpkg_integridade": integrity,
        "crs_pontos": point_info["crs"],
        "pontos": int(point_info["features"]),
        "fcu_poligonos": int(fcu_info["features"]),
        "ranking_campo": ranking_renderer.get("attr") if ranking_renderer is not None else None,
        "ranking_faixas": len(ranking_renderer.findall("./ranges/range")) if ranking_renderer is not None else 0,
        "prioridade_campo": action_renderer.get("attr") if action_renderer is not None else None,
        "fcu_campo": fcu_renderer.get("attr") if fcu_renderer is not None else None,
    }


def main() -> None:
    paths = dashboard_paths()
    for key in ("simple", "full", "ranking_source", "fcu_source"):
        if not paths[key].exists():
            raise FileNotFoundError(paths[key])

    folder = paths["folder"]
    folder.mkdir(parents=True, exist_ok=True)
    gpkg = folder / "preditor_fcu_salvador_qgis.gpkg"
    ranking_qml = folder / "01_ranking_qml_salvador.qml"
    action_qml = folder / "02_prioridade_modelo.qml"
    fcu_qml = folder / "03_fcu_tipos.qml"

    if gpkg.exists():
        gpkg.unlink()
    points = pyogrio.read_dataframe(paths["simple"], layer="salvador_saida")
    pyogrio.write_dataframe(
        points,
        gpkg,
        layer="salvador_saida",
        driver="GPKG",
        layer_options={"SPATIAL_INDEX": "YES"},
    )
    fcus = pyogrio.read_dataframe(paths["full"], layer="fcu_tipos")
    pyogrio.write_dataframe(
        fcus,
        gpkg,
        layer="fcu_tipos",
        driver="GPKG",
        append=True,
        layer_options={"SPATIAL_INDEX": "YES"},
    )

    ranking_summary = generate_ranking_qml(paths["ranking_source"], ranking_qml)
    generate_action_qml(action_qml)
    shutil.copy2(paths["fcu_source"], fcu_qml)
    write_readme(folder / "LEIA-ME_QGIS.txt")
    validation = validate_package(gpkg, ranking_qml, action_qml, fcu_qml)
    validation["ranking"] = ranking_summary
    validation["arquivo_bytes"] = gpkg.stat().st_size
    (folder / "VALIDACAO.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    zip_path = paths["zip"]
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(folder.iterdir()):
            if file.is_file():
                archive.write(file, arcname=f"QGIS_Salvador_Visualizacao/{file.name}")

    print(
        json.dumps(
            {
                "pasta": str(folder),
                "zip": str(zip_path),
                "zip_bytes": zip_path.stat().st_size,
                **validation,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
