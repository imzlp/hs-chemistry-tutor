#!/usr/bin/env python3
"""Build a concept-scoped review ledger for chemistry formula representations."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from formula_utils import (
    classify_formula,
    display_formula,
    formula_syntax_errors,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CANONICAL_DIR = DATA_DIR / "canonical"
REVIEW_DIR = DATA_DIR / "review"
CONCEPTS_PATH = CANONICAL_DIR / "concepts.jsonl"
OCCURRENCES_PATH = CANONICAL_DIR / "occurrences.jsonl"
OVERRIDES_PATH = ROOT / "scripts" / "formula_content_overrides.json"
OUTPUT_PATH = REVIEW_DIR / "formula-review.jsonl"
MANIFEST_PATH = REVIEW_DIR / "formula-review-manifest.json"


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


def formula_role_config(
    overrides: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    roles: dict[tuple[str, str], dict[str, Any]] = {}
    for concept_name, override in overrides.items():
        for entry in override["entries"]:
            formula = entry["formula"].strip()
            key = (concept_name, formula)
            if key in roles:
                raise ValueError(
                    f"duplicate formula role override: {concept_name} / {formula}"
                )
            roles[key] = entry
    return roles


def main() -> None:
    concepts = read_jsonl(CONCEPTS_PATH)
    occurrences = read_jsonl(OCCURRENCES_PATH)
    override_payload = load_json(OVERRIDES_PATH)
    reviewed_at = override_payload["reviewed_at"]
    roles = formula_role_config(override_payload["overrides"])

    occurrences_by_concept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occurrence in occurrences:
        occurrences_by_concept[occurrence["concept_id"]].append(occurrence)

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    formula_concepts = 0
    corrected_concepts = 0
    for concept in concepts:
        concept_id = concept["concept_id"]
        concept_name = concept["canonical_name"]
        formulas = concept["representations"]["formulas"]
        if not formulas:
            continue
        formula_concepts += 1
        concept_occurrences = occurrences_by_concept.get(concept_id, [])
        if not concept_occurrences:
            raise ValueError(f"{concept_id}: formula concept lacks occurrences")
        source_occurrence_ids = sorted(
            occurrence["occurrence_id"] for occurrence in concept_occurrences
        )
        source_refs = normalise_source_refs(concept_occurrences)
        if not source_refs:
            raise ValueError(f"{concept_id}: formula concept lacks textbook refs")
        concept_corrected = any(
            (concept_name, formula) in roles for formula in formulas
        )
        corrected_concepts += int(concept_corrected)

        for formula in formulas:
            syntax_errors = formula_syntax_errors(formula)
            if syntax_errors:
                raise ValueError(
                    f"{concept_id}: invalid formula {formula!r}: {syntax_errors}"
                )
            override = roles.get((concept_name, formula))
            formula_kind = classify_formula(formula)
            role = (
                override["role"]
                if override is not None
                else "mentioned_species"
            )
            note = (
                override["note"]
                if override is not None
                else (
                    "该化学式出现在本概念的教材摘要或规范化讲解中；"
                    "仅表示相关物种，不自动等同于概念的中心物质。"
                )
            )
            review_id = stable_id("fmr_", [concept_id, formula])
            if review_id in seen_ids:
                raise ValueError(
                    f"duplicate formula review ID for {concept_id}: {formula}"
                )
            seen_ids.add(review_id)
            records.append(
                {
                    "schema_version": "chem-formula-review-v1",
                    "formula_review_id": review_id,
                    "concept_id": concept_id,
                    "concept_name": concept_name,
                    "formula": formula,
                    "display_formula": display_formula(formula),
                    "formula_kind": formula_kind,
                    "role": role,
                    "note": note,
                    "review_method": (
                        "curated_formula_context"
                        if override is not None
                        else "machine_syntax_and_role_classification"
                    ),
                    "checks": {
                        "syntax": "passed",
                        "concept_scope": "typed_representation_not_identity_claim",
                        "textbook_context": "unverified_ai_summary",
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

    records.sort(
        key=lambda record: (
            record["concept_id"],
            record["formula"],
        )
    )
    method_counts = Counter(record["review_method"] for record in records)
    kind_counts = Counter(record["formula_kind"] for record in records)
    role_counts = Counter(record["role"] for record in records)
    manifest = {
        "schema_version": "chem-formula-review-manifest-v1",
        "generated_at": reviewed_at,
        "override_catalog_version": override_payload["version"],
        "formula_reviews": len(records),
        "canonical_concepts_with_formulas": formula_concepts,
        "unique_formula_strings": len({record["formula"] for record in records}),
        "curated_concepts": corrected_concepts,
        "review_methods": dict(sorted(method_counts.items())),
        "formula_kinds": dict(sorted(kind_counts.items())),
        "roles": dict(sorted(role_counts.items())),
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
            "机器审核只验证化学式语法、概念范围和表示类型，不认证物质存在、教材写法或具体实验条件。",
            "formulas 是概念范围内出现的化学式集合，不表示其中每一项都是该概念的中心物质；中心角色由 role 字段区分。",
            "所有页码继承自 AI 教材摘要，未核对出版社、版次、ISBN、版权页或印刷原文。",
            "HIn 等通用记号、含 n 的聚合物/通式以及受保护占位符不能被当作具体分子式解释。",
        ],
    }

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(format_jsonl(records), encoding="utf-8")
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"Wrote formula review to {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
