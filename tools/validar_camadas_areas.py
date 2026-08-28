from __future__ import annotations

from collections import Counter, defaultdict

from gerar_overview_qml import (
    QGIS_PALETTE,
    RANKING_RULES,
    candidate_class_key,
    iter_points,
    qgis_palette_index,
)


CLASSES = ("priority", "attention", "other")


def main() -> None:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    rank_min: dict[str, int] = {}
    rank_max: dict[str, int] = {}
    qml_classes: dict[str, set[int]] = defaultdict(set)
    for point in iter_points():
        area = str(point.get("a") or "")
        if not area:
            raise AssertionError("Célula sem área de estudo")
        rank = int(point.get("rt") or 0)
        if rank < 1:
            raise AssertionError(f"Ranking geral inválido em {area}: {rank}")
        counts[area][candidate_class_key(point)] += 1
        rank_min[area] = min(rank_min.get(area, rank), rank)
        rank_max[area] = max(rank_max.get(area, rank), rank)
        qml_classes[area].add(qgis_palette_index(rank, area))

    expected_areas = set(RANKING_RULES)
    if set(counts) != expected_areas:
        raise AssertionError(
            f"Áreas divergentes: dados={sorted(counts)}, regras={sorted(expected_areas)}"
        )

    print("area,total,attention_priority,attention,other,rank_min,rank_max,qml_colors,status")
    grand_total = 0
    for area in sorted(expected_areas):
        rule = RANKING_RULES[area]
        actual = counts[area]
        expected = {
            "priority": int(rule["priority_limit"]),
            "attention": int(rule["attention_count"]),
            "other": int(rule["other_count"]),
        }
        total = sum(actual[key] for key in CLASSES)
        if total != int(rule["total"]):
            raise AssertionError(f"Total divergente em {area}: {total} != {rule['total']}")
        if rank_min[area] != 1 or rank_max[area] != int(rule["total"]):
            raise AssertionError(
                f"Ranking local divergente em {area}: "
                f"{rank_min[area]}..{rank_max[area]} != 1..{rule['total']}"
            )
        if qml_classes[area] != set(range(len(QGIS_PALETTE))):
            raise AssertionError(
                f"QML incompleto em {area}: {len(qml_classes[area])} cores != "
                f"{len(QGIS_PALETTE)}"
            )
        for key in CLASSES:
            if actual[key] != expected[key]:
                raise AssertionError(
                    f"Classe divergente em {area}/{key}: {actual[key]} != {expected[key]}"
                )
        grand_total += total
        print(
            f"{area},{total},{actual['priority']},{actual['attention']},"
            f"{actual['other']},{rank_min[area]},{rank_max[area]},"
            f"{len(qml_classes[area])},OK"
        )

    print(f"TOTAL,{grand_total},-,-,-,-,-,-,OK")


if __name__ == "__main__":
    main()
