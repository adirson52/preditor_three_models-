from __future__ import annotations

from collections import Counter, defaultdict

from gerar_overview_qml import RANKING_RULES, candidate_class_key, iter_points


CLASSES = ("priority", "attention", "other")


def main() -> None:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for point in iter_points():
        area = str(point.get("a") or "")
        if not area:
            raise AssertionError("Célula sem área de estudo")
        counts[area][candidate_class_key(point)] += 1

    expected_areas = set(RANKING_RULES)
    if set(counts) != expected_areas:
        raise AssertionError(
            f"Áreas divergentes: dados={sorted(counts)}, regras={sorted(expected_areas)}"
        )

    print("area,total,attention_priority,attention,other,status")
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
        for key in CLASSES:
            if actual[key] != expected[key]:
                raise AssertionError(
                    f"Classe divergente em {area}/{key}: {actual[key]} != {expected[key]}"
                )
        grand_total += total
        print(
            f"{area},{total},{actual['priority']},{actual['attention']},"
            f"{actual['other']},OK"
        )

    print(f"TOTAL,{grand_total},-,-,-,OK")


if __name__ == "__main__":
    main()
