#!/usr/bin/env python3
"""Collapse quality flags into the controlled vocabulary in quality_flag_taxonomy.json."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TAXONOMY_PATH = ROOT / "scripts" / "quality_flag_taxonomy.json"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def format_jsonl(records: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def load_taxonomy() -> tuple[list[str], dict[str, str]]:
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    canonical_order = taxonomy["canonical_order"]
    groups = taxonomy["groups"]
    if set(canonical_order) != set(groups):
        raise ValueError("canonical_order and groups contain different flags")

    mapping: dict[str, str] = {}
    for canonical, aliases in groups.items():
        if not aliases:
            raise ValueError(f"{canonical}: alias list is empty")
        mapping[canonical] = canonical
        for alias in aliases:
            if alias in mapping and mapping[alias] != canonical:
                raise ValueError(f"{alias}: mapped more than once")
            mapping[alias] = canonical
    return canonical_order, mapping


def normalize_records(
    path: Path,
    records: list[dict[str, Any]],
    canonical_order: list[str],
    mapping: dict[str, str],
) -> tuple[int, Counter[str], Counter[str]]:
    changed = 0
    before = Counter()
    after = Counter()
    order = {flag: index for index, flag in enumerate(canonical_order)}

    for record in records:
        flags = record.get("quality_flags", [])
        if not isinstance(flags, list):
            raise ValueError(f"{path}: quality_flags is not a list")
        before.update(flags)
        unknown = sorted(set(flags) - set(mapping))
        if unknown:
            raise ValueError(f"{path} {record.get('kp_id')}: unknown flags {unknown}")

        normalized = sorted(
            {mapping[flag] for flag in flags},
            key=lambda flag: order[flag],
        )
        after.update(normalized)
        if normalized != flags:
            record["quality_flags"] = normalized
            changed += 1
    return changed, before, after


def validate(
    all_records: dict[str, list[dict[str, Any]]],
    canonical_order: list[str],
) -> None:
    allowed = set(canonical_order)
    for label, records in all_records.items():
        for record in records:
            flags = record.get("quality_flags")
            if not isinstance(flags, list):
                raise ValueError(f"{label} {record.get('kp_id')}: invalid quality_flags")
            if len(flags) != len(set(flags)):
                raise ValueError(f"{label} {record.get('kp_id')}: duplicate quality flags")
            unknown = set(flags) - allowed
            if unknown:
                raise ValueError(
                    f"{label} {record.get('kp_id')}: non-canonical flags {sorted(unknown)}"
                )


def write_if_changed(path: Path, records: list[dict[str, Any]]) -> bool:
    output = format_jsonl(records)
    original = path.read_text(encoding="utf-8")
    if output == original:
        return False
    path.write_text(output, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write normalized flags. Without this flag, only report planned changes.",
    )
    args = parser.parse_args()

    canonical_order, mapping = load_taxonomy()
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    book_ids = [book["book_id"] for book in manifest["books"]]
    all_records: dict[str, list[dict[str, Any]]] = {}
    before = Counter()
    after = Counter()
    changed_by_file: dict[str, int] = {}

    for kind in ("explicit", "teaching"):
        for book_id in book_ids:
            path = DATA_DIR / kind / f"{book_id}.{kind}.jsonl"
            label = f"{kind}/{book_id}"
            records = read_jsonl(path)
            changed, file_before, file_after = normalize_records(
                path, records, canonical_order, mapping
            )
            all_records[label] = records
            changed_by_file[label] = changed
            before.update(file_before)
            after.update(file_after)

    validate(all_records, canonical_order)

    print(f"Source vocabulary: {len(before)} flags, {sum(before.values())} assignments")
    print(f"Canonical vocabulary: {len(after)} flags, {sum(after.values())} assignments")
    print("Canonical distribution:")
    for flag in canonical_order:
        print(f"  {flag}: {after[flag]}")
    print("Changed records:")
    for label, changed in changed_by_file.items():
        print(f"  {label}: {changed}")

    if args.write:
        changed_files = []
        for kind in ("explicit", "teaching"):
            for book_id in book_ids:
                path = DATA_DIR / kind / f"{book_id}.{kind}.jsonl"
                label = f"{kind}/{book_id}"
                if write_if_changed(path, all_records[label]):
                    changed_files.append(str(path.relative_to(ROOT)))
        print(f"Wrote {len(changed_files)} files:")
        for path in changed_files:
            print(f"  {path}")
    else:
        print("Dry run only; pass --write to update files.")


if __name__ == "__main__":
    main()
