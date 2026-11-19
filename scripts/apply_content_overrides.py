#!/usr/bin/env python3
"""Apply reviewed field-level content overrides to JSONL knowledge records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_OVERRIDES = ROOT / "scripts" / "p0_content_overrides.json"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [
            json.loads(line, object_pairs_hook=reject_duplicate_keys)
            for line in handle
            if line.strip()
        ]


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate object keys instead of silently keeping the last value."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_json_config(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )


def format_jsonl(records: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def merge_fields(record: dict[str, Any], overrides: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(record.get(key), dict):
            nested_changed = merge_fields(record[key], value)
            changed.extend(f"{key}.{item}" for item in nested_changed)
        elif record.get(key) != value:
            record[key] = value
            changed.append(key)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write changes. Without this flag, only report planned changes.",
    )
    args = parser.parse_args()

    payload = load_json_config(args.overrides)
    overrides: dict[str, dict[str, Any]] = payload["overrides"]
    manifest = load_json_config(DATA_DIR / "manifest.json")
    book_ids = [book["book_id"] for book in manifest["books"]]

    seen: set[tuple[str, str]] = set()
    total_changes = 0
    changed_files: list[str] = []
    for kind in ("explicit", "teaching"):
        for book_id in book_ids:
            path = DATA_DIR / kind / f"{book_id}.{kind}.jsonl"
            records = read_jsonl(path)
            file_changes = 0
            for record in records:
                kp_id = record.get("kp_id")
                override = overrides.get(kp_id, {}).get(kind)
                if override is None:
                    continue
                seen.add((kind, kp_id))
                changed = merge_fields(record, override)
                if changed:
                    file_changes += 1
                    print(f"{kind}/{book_id} {kp_id}: {', '.join(changed)}")
            total_changes += file_changes
            output = format_jsonl(records)
            if args.write and output != path.read_text(encoding="utf-8"):
                path.write_text(output, encoding="utf-8")
                changed_files.append(str(path.relative_to(ROOT)))

    expected = {
        (kind, kp_id)
        for kp_id, value in overrides.items()
        for kind in ("explicit", "teaching")
        if kind in value
    }
    missing = sorted(expected - seen)
    if missing:
        raise ValueError(f"Override targets not found: {missing}")

    print(f"Targets: {len(seen)}; changed records: {total_changes}")
    if args.write:
        print(f"Wrote {len(changed_files)} files")
        for path in changed_files:
            print(f"  {path}")
    else:
        print("Dry run only; pass --write to update files.")


if __name__ == "__main__":
    main()
