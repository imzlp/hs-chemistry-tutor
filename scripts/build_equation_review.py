#!/usr/bin/env python3
"""Build the reviewed electrochemistry and organic equation layer."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from equation_balance import check_balance


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CANONICAL_DIR = DATA_DIR / "canonical"
REVIEW_DIR = DATA_DIR / "review"
CATALOG_PATH = ROOT / "scripts" / "equation_review_catalog.json"
CONCEPTS_PATH = CANONICAL_DIR / "concepts.jsonl"
OCCURRENCES_PATH = CANONICAL_DIR / "occurrences.jsonl"
OUTPUT_PATH = REVIEW_DIR / "equation-review.jsonl"
MANIFEST_PATH = REVIEW_DIR / "manifest.json"


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


def unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def normalise_source_refs(occurrences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    refs: list[dict[str, Any]] = []
    for occurrence in occurrences:
        for ref in occurrence.get("textbook_refs", []):
            key = json.dumps(ref, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            refs.append(
                {
                    "book_id": ref["book_id"],
                    "book_title": ref["book_title"],
                    "chapter": ref["chapter"],
                    "section": ref["section"],
                    "pages": ref["pages"],
                    "source_kind": ref["source_kind"],
                    "verification_status": "unverified_ai_summary_pages_only",
                }
            )
    return refs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    catalog = load_json(CATALOG_PATH)
    reviewed_at = catalog["reviewed_at"]
    concepts = read_jsonl(CONCEPTS_PATH)
    occurrences = read_jsonl(OCCURRENCES_PATH)
    concept_names = {
        concept["concept_id"]: concept["canonical_name"] for concept in concepts
    }
    occurrences_by_concept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occurrence in occurrences:
        occurrences_by_concept[occurrence["concept_id"]].append(occurrence)

    seen_set_ids: set[str] = set()
    records: list[dict[str, Any]] = []
    for review_set in catalog["sets"]:
        set_key = review_set["set_id"].strip()
        if not set_key or set_key in seen_set_ids:
            raise ValueError(f"invalid or duplicate equation review set ID: {set_key!r}")
        seen_set_ids.add(set_key)

        concept_ids = unique(review_set["concept_ids"])
        if not concept_ids:
            raise ValueError(f"{set_key}: no concept IDs")
        missing_concepts = [
            concept_id
            for concept_id in concept_ids
            if concept_id not in concept_names
        ]
        if missing_concepts:
            raise ValueError(
                f"{set_key}: unknown concept IDs: {missing_concepts}"
            )

        set_occurrences = [
            occurrence
            for concept_id in concept_ids
            for occurrence in occurrences_by_concept.get(concept_id, [])
        ]
        source_occurrence_ids = sorted(
            {occurrence["occurrence_id"] for occurrence in set_occurrences}
        )
        if not source_occurrence_ids:
            raise ValueError(f"{set_key}: no source occurrences")
        source_refs = normalise_source_refs(set_occurrences)
        if not source_refs:
            raise ValueError(f"{set_key}: no textbook references")

        roles: set[str] = set()
        review_set_id = stable_id("eqset_", set_key)
        for index, equation in enumerate(review_set["equations"], start=1):
            role = equation["role"].strip()
            display = equation["display"].strip()
            if not role or not display:
                raise ValueError(f"{set_key}: equation role/display is empty")
            if role in roles:
                raise ValueError(f"{set_key}: duplicate equation role: {role}")
            roles.add(role)

            machine_expression = equation.get("balance")
            if machine_expression:
                result = check_balance(machine_expression)
                if not result.mass_balanced or not result.charge_balanced:
                    raise ValueError(
                        f"{set_key}/{role}: machine balance failed: "
                        f"{machine_expression}"
                    )
                review_method = "machine_mass_charge_check"
                mass_status = "passed"
                charge_status = "passed"
            else:
                review_method = "structural_review"
                mass_status = "not_applicable"
                charge_status = "not_applicable"

            records.append(
                {
                    "schema_version": "chem-equation-review-v1",
                    "review_id": stable_id(
                        "eqr_", [set_key, index, role, display]
                    ),
                    "review_set_id": review_set_id,
                    "review_set_key": set_key,
                    "review_set_title": review_set["title"],
                    "domain": review_set["domain"],
                    "concept_ids": concept_ids,
                    "concept_names": [
                        concept_names[concept_id] for concept_id in concept_ids
                    ],
                    "medium": review_set["medium"],
                    "conditions": review_set["conditions"],
                    "set_notes": review_set["notes"],
                    "ambiguity_notes": review_set["ambiguity_notes"],
                    "equation_index": index,
                    "role": role,
                    "display": display,
                    "note": equation["note"],
                    "review_method": review_method,
                    "machine_expression": machine_expression,
                    "checks": {
                        "method": review_method,
                        "mass_balance": mass_status,
                        "charge_balance": charge_status,
                        "conditions": "metadata_only",
                        "state_symbols": "not_validated",
                    },
                    "source_occurrence_ids": source_occurrence_ids,
                    "source_refs": source_refs,
                    "source_verification": {
                        "status": "unverified_ai_summary_pages_only",
                        "publisher": None,
                        "edition": None,
                        "isbn": None,
                        "quote": None,
                        "quote_locator": None,
                        "page_ranges_inherited_from_source": True,
                    },
                    "review_status": "machine_reviewed",
                    "human_verified": False,
                    "evidence_status": "ai_textbook_summary_unverified",
                    "reviewed_at": reviewed_at,
                }
            )

    review_ids = [record["review_id"] for record in records]
    if len(review_ids) != len(set(review_ids)):
        raise ValueError("duplicate equation review IDs generated")

    records.sort(
        key=lambda record: (
            record["domain"],
            record["review_set_key"],
            record["equation_index"],
        )
    )
    method_counts = Counter(record["review_method"] for record in records)
    domain_counts = Counter(record["domain"] for record in records)
    concept_coverage = {
        concept_id for record in records for concept_id in record["concept_ids"]
    }
    source_occurrence_coverage = {
        occurrence_id
        for record in records
        for occurrence_id in record["source_occurrence_ids"]
    }
    manifest = {
        "schema_version": "chem-equation-review-manifest-v1",
        "generated_at": reviewed_at,
        "catalog_version": catalog["version"],
        "review_sets": len(seen_set_ids),
        "equations": len(records),
        "review_methods": dict(sorted(method_counts.items())),
        "domains": dict(sorted(domain_counts.items())),
        "canonical_concepts_covered": len(concept_coverage),
        "source_occurrences_covered": len(source_occurrence_coverage),
        "source_verification": {
            "status": "unverified_ai_summary_pages_only",
            "publisher_verified": 0,
            "edition_verified": 0,
            "isbn_verified": 0,
            "quote_verified": 0,
            "quote_locator_verified": 0,
        },
        "review_status": "machine_reviewed",
        "human_verified": False,
        "evidence_status": "ai_textbook_summary_unverified",
        "limitations": [
            "机器校验只覆盖组成式层面的原子守恒与净电荷守恒，不认证反应事实、条件、机理或教材原文。",
            "结构审查条目不能进行单一分子计量配平，必须连同介质、条件和结构片段说明使用。",
            "所有页码继承自 AI 教材摘要，未核对出版社、版次、ISBN、版权页或印刷原文。",
        ],
    }

    if args.no_write:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(format_jsonl(records), encoding="utf-8")
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"Wrote equation review to {REVIEW_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
