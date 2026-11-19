#!/usr/bin/env python3
"""Build an honest per-reference textbook locator ledger."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CANONICAL_DIR = DATA_DIR / "canonical"
REVIEW_DIR = DATA_DIR / "review"
MANIFEST_PATH = DATA_DIR / "manifest.json"
OCCURRENCES_PATH = CANONICAL_DIR / "occurrences.jsonl"
OUTPUT_PATH = REVIEW_DIR / "textbook-locator.jsonl"
LOCATOR_MANIFEST_PATH = REVIEW_DIR / "textbook-locator-manifest.json"
GENERATED_AT = "2026-11-19"


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [
            json.loads(line, object_pairs_hook=reject_duplicate_keys)
            for line in handle
            if line.strip()
        ]


def format_jsonl(records: list[dict[str, Any]]) -> str:
    return "\n".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        for record in records
    ) + "\n"


def stable_id(prefix: str, payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()[:12]


def main() -> None:
    manifest = load_json(MANIFEST_PATH)
    occurrences = read_jsonl(OCCURRENCES_PATH)
    manifest_book_ids = {book["book_id"] for book in manifest["books"]}

    rows: list[dict[str, Any]] = []
    occurrence_ids: set[str] = set()
    for occurrence in occurrences:
        occurrence_id = occurrence["occurrence_id"]
        if occurrence_id in occurrence_ids:
            raise ValueError(f"duplicate occurrence ID: {occurrence_id}")
        occurrence_ids.add(occurrence_id)
        if occurrence["book_id"] not in manifest_book_ids:
            raise ValueError(
                f"{occurrence_id}: unknown book ID {occurrence['book_id']}"
            )
        refs = occurrence.get("textbook_refs", [])
        if not refs:
            raise ValueError(f"{occurrence_id}: no textbook references")
        for ref_index, ref in enumerate(refs, start=1):
            if ref["pages"] != sorted(ref["pages"]):
                raise ValueError(
                    f"{occurrence_id}: textbook page range is not ascending: "
                    f"{ref['pages']}"
                )
            rows.append(
                {
                    "schema_version": "chem-textbook-locator-v1",
                    "locator_id": stable_id(
                        "tloc_", [occurrence_id, ref_index, ref]
                    ),
                    "occurrence_id": occurrence_id,
                    "concept_id": occurrence["concept_id"],
                    "source_ref_index": ref_index,
                    "book_id": ref["book_id"],
                    "book_title": ref["book_title"],
                    "chapter": ref["chapter"],
                    "section": ref["section"],
                    "pages": ref["pages"],
                    "source_kind": ref["source_kind"],
                    "publisher": None,
                    "edition": None,
                    "isbn": None,
                    "quote": None,
                    "quote_locator": None,
                    "page_ranges_inherited_from_ai_summary": True,
                    "verification_status": "unverified_ai_summary_pages_only",
                    "review_status": "unverified",
                    "human_verified": False,
                    "verified_at": None,
                    "verified_by": None,
                    "evidence_status": "ai_textbook_summary_unverified",
                    "generated_at": GENERATED_AT,
                }
            )

    expected_occurrences = {
        book["book_id"]: book["kp_count"] for book in manifest["books"]
    }
    actual_occurrences = Counter(row["book_id"] for row in occurrences)
    if dict(actual_occurrences) != expected_occurrences:
        raise ValueError(
            "occurrence counts differ from manifest: "
            f"{dict(actual_occurrences)} != {expected_occurrences}"
        )

    locator_ids = [row["locator_id"] for row in rows]
    if len(locator_ids) != len(set(locator_ids)):
        raise ValueError("duplicate textbook locator IDs generated")
    rows.sort(
        key=lambda row: (
            row["book_id"],
            row["occurrence_id"],
            row["source_ref_index"],
        )
    )

    refs_by_book = Counter(row["book_id"] for row in rows)
    occurrences_by_book = Counter(
        occurrence["book_id"] for occurrence in occurrences
    )
    output_manifest = {
        "schema_version": "chem-textbook-locator-manifest-v1",
        "generated_at": GENERATED_AT,
        "source_occurrences": len(occurrence_ids),
        "locator_rows": len(rows),
        "books": [
            {
                "book_id": book_id,
                "book_title": next(
                    book["book_title"]
                    for book in manifest["books"]
                    if book["book_id"] == book_id
                ),
                "occurrences": occurrences_by_book[book_id],
                "textbook_refs": refs_by_book[book_id],
                "publisher": None,
                "edition": None,
                "isbn": None,
                "verification_status": "unverified_ai_summary_pages_only",
            }
            for book_id in sorted(refs_by_book)
        ],
        "verified_metadata": {
            "publisher": 0,
            "edition": 0,
            "isbn": 0,
            "quote": 0,
            "quote_locator": 0,
        },
        "verification_status": "unverified_ai_summary_pages_only",
        "human_verified": False,
        "evidence_status": "ai_textbook_summary_unverified",
        "blocking_inputs": [
            "仓库中没有五本教材的封面、版权页、版次页或 ISBN 记录。",
            "现有 pages 是 AI 摘要声明的页码范围，未与印刷页或 PDF 页逐条比对。",
            "仓库中没有可引用的教材原文，因此 quote 与 quote_locator 必须保持 null。",
        ],
    }

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(format_jsonl(rows), encoding="utf-8")
    LOCATOR_MANIFEST_PATH.write_text(
        json.dumps(output_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output_manifest, ensure_ascii=False, indent=2))
    print(f"Wrote textbook locator ledger to {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
