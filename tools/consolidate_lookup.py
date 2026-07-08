import gzip
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data_tiles" / "final" / "id_lookup" / "12"
TARGET = ROOT / "data_tiles" / "final" / "id_lookup" / "8"


def load_lookup(path: Path) -> list:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("p", [])


def write_lookup(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump({"p": records}, f, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    grouped = defaultdict(list)
    files = sorted(SOURCE.glob("*.json.gz"))
    if not files:
        raise SystemExit(f"No lookup files found in {SOURCE}")

    for path in files:
        for record in load_lookup(path):
            if not record:
                continue
            cell_id = str(record[0])
            grouped[cell_id[:8]].append(record)

    for prefix, records in grouped.items():
        records.sort(key=lambda r: str(r[0]))
        write_lookup(TARGET / f"{prefix}.json.gz", records)

    print(f"source_files={len(files)}")
    print(f"target_files={len(grouped)}")
    print(f"target_dir={TARGET}")


if __name__ == "__main__":
    main()
