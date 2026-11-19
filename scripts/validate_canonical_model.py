#!/usr/bin/env python3
"""Validate the canonical chemistry model and its source-occurrence coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from equation_balance import check_balance


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CANONICAL_DIR = DATA_DIR / "canonical"
REVIEW_DIR = DATA_DIR / "review"
SCHEMA_PATH = DATA_DIR / "schema" / "chem-concept-v1.schema.json"
CONFUSABLE_SCHEMA_PATH = DATA_DIR / "schema" / "chem-confusable-pair-v1.schema.json"
EQUATION_SCHEMA_PATH = DATA_DIR / "schema" / "chem-equation-review-v1.schema.json"
LOCATOR_SCHEMA_PATH = DATA_DIR / "schema" / "chem-textbook-locator-v1.schema.json"
EQUATION_REVIEW_PATH = REVIEW_DIR / "equation-review.jsonl"
EQUATION_MANIFEST_PATH = REVIEW_DIR / "manifest.json"
LOCATOR_PATH = REVIEW_DIR / "textbook-locator.jsonl"
LOCATOR_MANIFEST_PATH = REVIEW_DIR / "textbook-locator-manifest.json"
P0_PATH = ROOT / "scripts" / "p0_content_overrides.json"
P1_PATH = ROOT / "scripts" / "p1_content_overrides.json"
P2_PATH = ROOT / "scripts" / "p2_content_overrides.json"
RELATION_STATUSES = {
    "resolved",
    "unresolved",
    "ambiguous",
    "self_reference",
    "external_prior",
}
RELATION_METHODS = {
    "exact_label",
    "exact_label_normalized",
    "manual_label_map",
    "normalized_label",
    "external_prior",
    "none",
}
STUDENT_META_RE = re.compile(
    r"教学中|教师|需强调|引导学生|课堂上|本知识点|教学重点|教学应|应强调|"
    r"应引导|让学生|使学生|学生应|学生需|考查|考点|易错|易混"
)
SCOPE_META_RE = re.compile(
    r"本节|本章|本知识点|教材|栏目|习题|实验活动|引言|帮助(?:学生|理解)|"
    r"便于学生|引导学生|讲解|教学|学习时|用于教学|重点|复习|考试|考点|"
    r"知识梳理|课堂|教师"
)


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
            raise ValueError(f"duplicate JSON key in {key!r}")
        result[key] = value
    return result


def load_json_config(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )


def fingerprint(*records: dict[str, Any]) -> str:
    payload = json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def merge_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(
            key in actual and merge_matches(actual[key], value)
            for key, value in expected.items()
        )
    return actual == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-schema", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    manifest = load_json_config(DATA_DIR / "manifest.json")
    model_manifest = load_json_config(CANONICAL_DIR / "manifest.json")
    concepts = read_jsonl(CANONICAL_DIR / "concepts.jsonl")
    occurrences = read_jsonl(CANONICAL_DIR / "occurrences.jsonl")
    relations = read_jsonl(CANONICAL_DIR / "relations.jsonl")
    review_queue = read_jsonl(CANONICAL_DIR / "review-queue.jsonl")
    relation_gaps = read_jsonl(CANONICAL_DIR / "relation-gaps.jsonl")
    confusable_pairs = read_jsonl(CANONICAL_DIR / "confusable-pairs.jsonl")
    review_sheet = read_jsonl(CANONICAL_DIR / "review-sheet.jsonl")
    equation_reviews = read_jsonl(EQUATION_REVIEW_PATH)
    equation_review_manifest = load_json_config(EQUATION_MANIFEST_PATH)
    textbook_locators = read_jsonl(LOCATOR_PATH)
    textbook_locator_manifest = load_json_config(LOCATOR_MANIFEST_PATH)

    book_ids = [book["book_id"] for book in manifest["books"]]
    source_explicit: dict[str, dict[str, Any]] = {}
    source_teaching: dict[str, dict[str, Any]] = {}
    source_by_book: dict[str, list[dict[str, Any]]] = {}
    teaching_by_book: dict[str, list[dict[str, Any]]] = {}
    for book in manifest["books"]:
        book_id = book["book_id"]
        explicit = read_jsonl(DATA_DIR / "explicit" / f"{book_id}.explicit.jsonl")
        teaching = read_jsonl(DATA_DIR / "teaching" / f"{book_id}.teaching.jsonl")
        source_by_book[book_id] = explicit
        teaching_by_book[book_id] = teaching
        check(
            len(explicit) == book["kp_count"],
            f"{book_id}: explicit count differs from source manifest",
        )
        check(
            len(teaching) == book["teaching_count"],
            f"{book_id}: teaching count differs from source manifest",
        )
        explicit_ids = {record["kp_id"] for record in explicit}
        teaching_ids = {record["kp_id"] for record in teaching}
        check(
            explicit_ids == teaching_ids,
            f"{book_id}: explicit and teaching IDs differ",
        )
        for record in explicit:
            check(
                record["kp_id"] not in source_explicit,
                f"duplicate source explicit ID: {record['kp_id']}",
            )
            source_explicit[record["kp_id"]] = record
        for record in teaching:
            check(
                record["kp_id"] not in source_teaching,
                f"duplicate source teaching ID: {record['kp_id']}",
            )
            source_teaching[record["kp_id"]] = record

    source_ids = set(source_explicit)
    check(
        len(source_ids) == 562,
        f"expected 562 source occurrences, got {len(source_ids)}",
    )
    check(
        model_manifest["source_occurrences"] == len(source_ids),
        "canonical manifest source_occurrences mismatch",
    )
    check(
        model_manifest["canonical_concepts"] == len(concepts),
        "canonical manifest concept count mismatch",
    )
    check(
        model_manifest["confusable_pairs"] == len(confusable_pairs),
        "canonical manifest confusable pair count mismatch",
    )
    check(
        model_manifest["review_sheet_rows"] == len(review_sheet),
        "canonical manifest review-sheet count mismatch",
    )
    check(
        model_manifest["review_sheet_priorities"]
        == dict(
            sorted(Counter(row["review_priority"] for row in review_sheet).items())
        ),
        "canonical manifest review-sheet priorities mismatch",
    )
    check(
        model_manifest["source_records"]["explicit"] == len(source_explicit),
        "canonical manifest explicit count mismatch",
    )
    check(
        model_manifest["source_records"]["teaching"] == len(source_teaching),
        "canonical manifest teaching count mismatch",
    )
    check(
        model_manifest["relation_gaps"]["labels"] == len(relation_gaps),
        "canonical manifest relation-gap label count mismatch",
    )
    check(
        model_manifest["relation_gaps"]["relations"]
        == sum(row["relation_count"] for row in relation_gaps),
        "canonical manifest relation-gap relation count mismatch",
    )
    check(
        model_manifest["equation_review"]["equations"] == len(equation_reviews),
        "canonical manifest equation review count mismatch",
    )
    check(
        model_manifest["equation_review"]["review_sets"]
        == equation_review_manifest["review_sets"],
        "canonical manifest equation review-set count mismatch",
    )
    check(
        model_manifest["equation_review"]["machine_mass_charge_checked"]
        == equation_review_manifest["review_methods"][
            "machine_mass_charge_check"
        ],
        "canonical manifest machine-checked equation count mismatch",
    )
    check(
        model_manifest["equation_review"]["structural_reviewed"]
        == equation_review_manifest["review_methods"]["structural_review"],
        "canonical manifest structural-review equation count mismatch",
    )
    check(
        textbook_locator_manifest["source_occurrences"] == len(source_ids),
        "textbook locator occurrence count mismatch",
    )
    check(
        textbook_locator_manifest["locator_rows"] == len(textbook_locators),
        "textbook locator row count mismatch",
    )

    concept_by_id = {concept["concept_id"]: concept for concept in concepts}
    check(
        len(concept_by_id) == len(concepts),
        "duplicate concept_id in canonical concepts",
    )
    concept_by_name = {concept["canonical_name"]: concept for concept in concepts}
    check(
        len(concept_by_name) == len(concepts),
        "duplicate canonical_name in canonical concepts",
    )

    review_sheet_by_id = {row["concept_id"]: row for row in review_sheet}
    check(
        len(review_sheet_by_id) == len(review_sheet),
        "duplicate concept_id in review-sheet",
    )
    check(
        set(review_sheet_by_id) == set(concept_by_id),
        "review-sheet does not exactly cover canonical concepts",
    )
    for row in review_sheet:
        concept = concept_by_id.get(row["concept_id"])
        check(concept is not None, f"review-sheet references missing concept: {row['concept_id']}")
        if concept is None:
            continue
        check(
            row["canonical_name"] == concept["canonical_name"],
            f"{row['concept_id']}: review-sheet name mismatch",
        )
        check(
            row["review_priority"] in {"high", "medium", "baseline"},
            f"{row['concept_id']}: invalid review priority",
        )
        check(
            isinstance(row.get("field_checks"), dict)
            and all(isinstance(value, bool) for value in row["field_checks"].values()),
            f"{row['concept_id']}: invalid review field checks",
        )
        check(
            "scope_specific" in row.get("field_checks", {}),
            f"{row['concept_id']}: review-sheet lacks scope_specific check",
        )
        check(
            row.get("human_verified") is False,
            f"{row['concept_id']}: review-sheet must not claim human review",
        )
        check(
            row.get("evidence_status") == "ai_textbook_summary_unverified",
            f"{row['concept_id']}: review-sheet evidence status mismatch",
        )
        check(
            bool(row.get("review_focus")),
            f"{row['concept_id']}: review-sheet lacks review focus",
        )

    occurrence_by_id = {row["occurrence_id"]: row for row in occurrences}
    check(
        len(occurrence_by_id) == len(occurrences),
        "duplicate occurrence_id in occurrences.jsonl",
    )
    check(
        set(occurrence_by_id) == source_ids,
        "occurrence IDs do not exactly cover source kp_ids",
    )

    equation_review_ids: set[str] = set()
    equation_review_by_concept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    equation_set_metadata: dict[str, dict[str, Any]] = {}
    equation_set_roles: dict[str, set[str]] = defaultdict(set)
    equation_method_counts: Counter[str] = Counter()
    equation_domain_counts: Counter[str] = Counter()
    equation_occurrence_coverage: set[str] = set()
    for review in equation_reviews:
        review_id = review["review_id"]
        check(
            review["schema_version"] == "chem-equation-review-v1",
            f"{review_id}: equation review schema version mismatch",
        )
        check(
            review_id not in equation_review_ids,
            f"duplicate equation review ID: {review_id}",
        )
        equation_review_ids.add(review_id)
        check(
            review["domain"] in {"electrochemistry", "organic_chemistry"},
            f"{review_id}: invalid equation domain",
        )
        check(
            review["review_status"] == "machine_reviewed",
            f"{review_id}: equation review status mismatch",
        )
        check(
            review["human_verified"] is False,
            f"{review_id}: equation review must not claim human verification",
        )
        check(
            review["evidence_status"] == "ai_textbook_summary_unverified",
            f"{review_id}: equation review evidence status mismatch",
        )
        check(
            re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", review["reviewed_at"])
            is not None,
            f"{review_id}: invalid equation review date",
        )
        check(
            len(review["concept_ids"]) == len(review["concept_names"]),
            f"{review_id}: concept ID/name length mismatch",
        )
        for concept_id, concept_name in zip(
            review["concept_ids"], review["concept_names"]
        ):
            concept = concept_by_id.get(concept_id)
            check(
                concept is not None,
                f"{review_id}: unknown concept ID {concept_id}",
            )
            if concept is not None:
                check(
                    concept["canonical_name"] == concept_name,
                    f"{review_id}: concept name mismatch for {concept_id}",
                )
            equation_review_by_concept[concept_id].append(review)

        set_key = review["review_set_key"]
        check(
            review["role"] not in equation_set_roles[set_key],
            f"{review_id}: duplicate equation role in set {set_key}",
        )
        equation_set_roles[set_key].add(review["role"])
        set_metadata = {
            field: review[field]
            for field in (
                "review_set_id",
                "review_set_key",
                "review_set_title",
                "domain",
                "concept_ids",
                "concept_names",
                "medium",
                "conditions",
                "set_notes",
                "ambiguity_notes",
                "source_occurrence_ids",
                "source_refs",
            )
        }
        existing_metadata = equation_set_metadata.get(set_key)
        if existing_metadata is None:
            equation_set_metadata[set_key] = set_metadata
        else:
            check(
                existing_metadata == set_metadata,
                f"{review_id}: inconsistent metadata within set {set_key}",
            )

        method = review["review_method"]
        equation_method_counts[method] += 1
        equation_domain_counts[review["domain"]] += 1
        check(
            review["checks"]["method"] == method,
            f"{review_id}: equation check method mismatch",
        )
        check(
            review["checks"]["conditions"] == "metadata_only",
            f"{review_id}: equation conditions must not claim validation",
        )
        check(
            review["checks"]["state_symbols"] == "not_validated",
            f"{review_id}: equation state symbols must not claim validation",
        )
        machine_expression = review["machine_expression"]
        if method == "machine_mass_charge_check":
            check(
                isinstance(machine_expression, str)
                and bool(machine_expression.strip()),
                f"{review_id}: machine check lacks expression",
            )
            check(
                review["checks"]["mass_balance"] == "passed"
                and review["checks"]["charge_balance"] == "passed",
                f"{review_id}: machine check status is not passed",
            )
            if isinstance(machine_expression, str) and machine_expression.strip():
                try:
                    balance = check_balance(machine_expression)
                except Exception as exc:
                    errors.append(
                        f"{review_id}: machine expression parse failed: {exc}"
                    )
                else:
                    check(
                        balance.mass_balanced,
                        f"{review_id}: machine expression is not mass balanced",
                    )
                    check(
                        balance.charge_balanced,
                        f"{review_id}: machine expression is not charge balanced",
                    )
        elif method == "structural_review":
            check(
                machine_expression is None,
                f"{review_id}: structural review must not carry machine expression",
            )
            check(
                review["checks"]["mass_balance"] == "not_applicable"
                and review["checks"]["charge_balance"] == "not_applicable",
                f"{review_id}: structural review check status mismatch",
            )
        else:
            errors.append(f"{review_id}: invalid equation review method")

        for occurrence_id in review["source_occurrence_ids"]:
            occurrence = occurrence_by_id.get(occurrence_id)
            check(
                occurrence is not None,
                f"{review_id}: unknown source occurrence {occurrence_id}",
            )
            if occurrence is not None:
                check(
                    occurrence["concept_id"] in review["concept_ids"],
                    f"{review_id}: source occurrence belongs to another concept",
                )
            equation_occurrence_coverage.add(occurrence_id)

        expected_occurrences = {
            occurrence_id
            for occurrence_id, occurrence in occurrence_by_id.items()
            if occurrence["concept_id"] in review["concept_ids"]
        }
        check(
            set(review["source_occurrence_ids"]) == expected_occurrences,
            f"{review_id}: source occurrence coverage mismatch",
        )
        expected_ref_keys = {
            json.dumps(
                {
                    "book_id": ref["book_id"],
                    "book_title": ref["book_title"],
                    "chapter": ref["chapter"],
                    "section": ref["section"],
                    "pages": ref["pages"],
                    "source_kind": ref["source_kind"],
                    "verification_status": "unverified_ai_summary_pages_only",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            for occurrence_id in expected_occurrences
            for ref in occurrence_by_id[occurrence_id].get("textbook_refs", [])
        }
        actual_ref_keys = {
            json.dumps(ref, ensure_ascii=False, sort_keys=True)
            for ref in review["source_refs"]
        }
        check(
            actual_ref_keys == expected_ref_keys,
            f"{review_id}: source reference coverage mismatch",
        )

        check(
            bool(review["source_refs"]),
            f"{review_id}: equation review lacks source refs",
        )
        for ref in review["source_refs"]:
            check(
                ref["verification_status"]
                == "unverified_ai_summary_pages_only",
                f"{review_id}: source ref claims verification",
            )
        source_verification = review["source_verification"]
        check(
            source_verification["status"]
            == "unverified_ai_summary_pages_only",
            f"{review_id}: source verification status mismatch",
        )
        for field in ("publisher", "edition", "isbn", "quote", "quote_locator"):
            check(
                source_verification[field] is None,
                f"{review_id}: source verification field {field} must be null",
            )
        check(
            source_verification["page_ranges_inherited_from_source"] is True,
            f"{review_id}: source page provenance flag mismatch",
        )

    check(
        equation_review_manifest["review_sets"] == len(equation_set_metadata),
        "equation review manifest set count mismatch",
    )
    check(
        len(
            {
                metadata["review_set_id"]
                for metadata in equation_set_metadata.values()
            }
        )
        == len(equation_set_metadata),
        "equation review set IDs are not unique",
    )
    check(
        equation_review_manifest["equations"] == len(equation_reviews),
        "equation review manifest equation count mismatch",
    )
    check(
        equation_review_manifest["review_methods"]
        == dict(sorted(equation_method_counts.items())),
        "equation review manifest method counts mismatch",
    )
    check(
        equation_review_manifest["domains"]
        == dict(sorted(equation_domain_counts.items())),
        "equation review manifest domain counts mismatch",
    )
    check(
        equation_review_manifest["canonical_concepts_covered"]
        == len(equation_review_by_concept),
        "equation review manifest concept coverage mismatch",
    )
    check(
        equation_review_manifest["source_occurrences_covered"]
        == len(equation_occurrence_coverage),
        "equation review manifest source coverage mismatch",
    )
    check(
        equation_review_manifest["human_verified"] is False,
        "equation review manifest must not claim human verification",
    )
    check(
        equation_review_manifest["review_status"] == "machine_reviewed",
        "equation review manifest status mismatch",
    )
    check(
        equation_review_manifest["evidence_status"]
        == "ai_textbook_summary_unverified",
        "equation review manifest evidence status mismatch",
    )

    for concept in concepts:
        reviews = equation_review_by_concept.get(concept["concept_id"], [])
        quality = concept["quality"]
        if not reviews:
            check(
                quality["equation_review_ids"] == [],
                f"{concept['concept_id']}: unreviewed concept has equation review IDs",
            )
            check(
                quality["equation_validation_status"] == "not_reviewed",
                f"{concept['concept_id']}: unreviewed concept has validation status",
            )
            continue
        ordered = sorted(
            reviews,
            key=lambda record: (
                record["review_set_key"],
                record["equation_index"],
            ),
        )
        expected_ids = list(dict.fromkeys(
            record["review_id"] for record in ordered
        ))
        check(
            quality["equation_review_ids"] == expected_ids,
            f"{concept['concept_id']}: equation review IDs mismatch",
        )
        expected_displays = list(dict.fromkeys(
            record["display"] for record in ordered
        ))
        check(
            concept["representations"]["equations"] == expected_displays,
            f"{concept['concept_id']}: reviewed equations do not match representations",
        )
        methods = {record["review_method"] for record in ordered}
        if methods == {"machine_mass_charge_check"}:
            expected_status = "machine_mass_charge_checked"
        elif methods == {"structural_review"}:
            expected_status = "structural_reviewed"
        else:
            expected_status = "machine_and_structural_reviewed"
        check(
            quality["equation_validation_status"] == expected_status,
            f"{concept['concept_id']}: equation validation status mismatch",
        )
        issue_codes = {
            detail["code"] for detail in quality["issue_details"]
        }
        check(
            "equation_extraction_unverified" not in issue_codes,
            f"{concept['concept_id']}: reviewed concept retains extraction warning",
        )
        check(
            "equation_textbook_evidence_unverified" in issue_codes,
            f"{concept['concept_id']}: reviewed concept hides textbook evidence gap",
        )

    occurrence_ids_by_concept: dict[str, list[str]] = defaultdict(list)
    for row in occurrences:
        occurrence_ids_by_concept[row["concept_id"]].append(row["occurrence_id"])
        check(
            row["concept_id"] in concept_by_id,
            f"occurrence {row['occurrence_id']} references missing concept",
        )
        check(
            row.get("source_fingerprint")
            == fingerprint(
                source_explicit[row["occurrence_id"]],
                source_teaching[row["occurrence_id"]],
            ),
            f"occurrence {row['occurrence_id']} source fingerprint mismatch",
        )

    locator_ids: set[str] = set()
    locator_occurrences: set[str] = set()
    locator_counts_by_book: Counter[str] = Counter()
    for locator in textbook_locators:
        locator_id = locator["locator_id"]
        check(
            locator_id not in locator_ids,
            f"duplicate textbook locator ID: {locator_id}",
        )
        locator_ids.add(locator_id)
        check(
            locator["schema_version"] == "chem-textbook-locator-v1",
            f"{locator_id}: textbook locator schema version mismatch",
        )
        occurrence_id = locator["occurrence_id"]
        locator_occurrences.add(occurrence_id)
        occurrence = occurrence_by_id.get(occurrence_id)
        check(
            occurrence is not None,
            f"{locator_id}: unknown occurrence {occurrence_id}",
        )
        if occurrence is None:
            continue
        check(
            locator["concept_id"] == occurrence["concept_id"],
            f"{locator_id}: concept mapping mismatch",
        )
        check(
            locator["book_id"] == occurrence["book_id"],
            f"{locator_id}: book ID mismatch",
        )
        ref_index = locator["source_ref_index"]
        refs = occurrence.get("textbook_refs", [])
        check(
            1 <= ref_index <= len(refs),
            f"{locator_id}: source ref index out of range",
        )
        if 1 <= ref_index <= len(refs):
            ref = refs[ref_index - 1]
            check(
                locator["pages"] == sorted(locator["pages"]),
                f"{locator_id}: textbook page range is not ascending",
            )
            for field in (
                "book_id",
                "book_title",
                "chapter",
                "section",
                "pages",
                "source_kind",
            ):
                check(
                    locator[field] == ref[field],
                    f"{locator_id}: source ref field mismatch: {field}",
                )
        check(
            locator["publisher"] is None
            and locator["edition"] is None
            and locator["isbn"] is None
            and locator["quote"] is None
            and locator["quote_locator"] is None,
            f"{locator_id}: textbook metadata must remain null",
        )
        check(
            locator["page_ranges_inherited_from_ai_summary"] is True,
            f"{locator_id}: textbook page provenance flag mismatch",
        )
        check(
            locator["verification_status"]
            == "unverified_ai_summary_pages_only",
            f"{locator_id}: textbook locator verification status mismatch",
        )
        check(
            locator["review_status"] == "unverified",
            f"{locator_id}: textbook locator review status mismatch",
        )
        check(
            locator["human_verified"] is False,
            f"{locator_id}: textbook locator must not claim human verification",
        )
        check(
            locator["verified_at"] is None and locator["verified_by"] is None,
            f"{locator_id}: textbook locator must not claim verification actors",
        )
        check(
            locator["evidence_status"] == "ai_textbook_summary_unverified",
            f"{locator_id}: textbook locator evidence status mismatch",
        )
        locator_counts_by_book[locator["book_id"]] += 1

    check(
        locator_occurrences == source_ids,
        "textbook locator rows do not cover every source occurrence",
    )
    expected_locator_books = {
        row["book_id"]: row["textbook_refs"]
        for row in textbook_locator_manifest["books"]
    }
    for row in textbook_locator_manifest["books"]:
        check(
            row["publisher"] is None
            and row["edition"] is None
            and row["isbn"] is None,
            f"{row['book_id']}: textbook manifest claims unverified metadata",
        )
        check(
            row["verification_status"]
            == "unverified_ai_summary_pages_only",
            f"{row['book_id']}: textbook manifest verification status mismatch",
        )
    check(
        dict(locator_counts_by_book) == expected_locator_books,
        "textbook locator manifest book counts mismatch",
    )
    check(
        textbook_locator_manifest["verified_metadata"]
        == {
            "publisher": 0,
            "edition": 0,
            "isbn": 0,
            "quote": 0,
            "quote_locator": 0,
        },
        "textbook locator manifest claims verified metadata",
    )
    check(
        textbook_locator_manifest["human_verified"] is False,
        "textbook locator manifest must not claim human verification",
    )
    check(
        textbook_locator_manifest["verification_status"]
        == "unverified_ai_summary_pages_only",
        "textbook locator manifest verification status mismatch",
    )

    for concept in concepts:
        source_ids_for_concept = concept["provenance"]["occurrence_ids"]
        check(
            sorted(source_ids_for_concept)
            == sorted(occurrence_ids_by_concept[concept["concept_id"]]),
            f"{concept['concept_id']}: occurrence provenance mismatch",
        )
        check(
            concept["provenance"]["primary_explicit_occurrence_id"]
            in source_ids_for_concept,
            f"{concept['concept_id']}: primary explicit occurrence not in provenance",
        )
        check(
            concept["provenance"]["primary_teaching_occurrence_id"]
            in source_ids_for_concept,
            f"{concept['concept_id']}: primary teaching occurrence not in provenance",
        )
        check(
            concept["definition"]["statement"].strip() != "",
            f"{concept['concept_id']}: empty definition statement",
        )
        check(
            concept["teaching"]["student_explanation"].strip() != "",
            f"{concept['concept_id']}: empty student explanation",
        )
        check(
            not SCOPE_META_RE.search(concept["definition"]["scope"]),
            f"{concept['concept_id']}: definition scope contains editorial/meta language",
        )
        check(
            "的核心含义、适用条件和典型应用" not in concept["definition"]["scope"],
            f"{concept['concept_id']}: generic fallback scope remains",
        )
        check(
            not STUDENT_META_RE.search(concept["teaching"]["student_explanation"]),
            f"{concept['concept_id']}: student explanation contains teacher/meta language",
        )
        definition_parts = (
            set(concept["definition"]["conditions"])
            | set(concept["definition"]["exceptions"])
        )
        check(
            not definition_parts.intersection(concept["definition"]["boundary_notes"]),
            f"{concept['concept_id']}: boundary notes duplicate conditions/exceptions",
        )
        check(
            all(
                "适用范围" not in example and "适用条件" not in example
                for example in concept["examples"]
            ),
            f"{concept['concept_id']}: examples contain scope/condition scaffolding",
        )
        check(
            concept["quality"]["review_status"] != "expert_verified",
            f"{concept['concept_id']}: expert_verified must not be emitted automatically",
        )
        check(
            concept["quality"]["human_verified"] is False,
            f"{concept['concept_id']}: human_verified must be false in this run",
        )
        check(
            concept["quality"]["evidence_status"]
            == "ai_textbook_summary_unverified",
            f"{concept['concept_id']}: evidence_status must remain unverified",
        )
        check(
            concept["provenance"]["evidence_status"]
            == "ai_textbook_summary_unverified",
            f"{concept['concept_id']}: provenance evidence_status must remain unverified",
        )
        for detail in concept["quality"]["issue_details"]:
            check(
                detail.get("code") and detail.get("message"),
                f"{concept['concept_id']}: issue detail lacks code/message",
            )
            check(
                detail.get("severity") in {"review", "blocking"},
                f"{concept['concept_id']}: invalid issue severity",
            )

    # High-risk corrections are pinned as regressions. These checks are not a
    # substitute for expert review; they prevent known bad summaries from
    # silently returning during a future rebuild.
    regression_expectations = {
        "硝酸的物理性质与强氧化性": {
            "required": ("浓硝酸", "稀硝酸", "钝化"),
            "forbidden": ("常温下使铁铝钝化",),
        },
        "氢氧燃料电池工作原理": {
            "required": ("酸性", "碱性", "不能把酸性体系直接套用"),
            "forbidden": (),
        },
        "抗坏血酸的抗氧化机理": {
            "required": ("自身被氧化", "不能简单写成“消耗氧气”"),
            "forbidden": ("通过被氧化为脱氢抗坏血酸来消耗氧气",),
        },
        "纤维素的化学性质与实验": {
            "required": ("较强酸", "约 90% 硫酸", "炭化"),
            "forbidden": ("稀酸或酶催化并加热", "纤维素水解通常使用稀酸"),
        },
        "纤维素的非还原性": {
            "required": ("糖苷键", "半缩醛端基", "水解生成葡萄糖后"),
            "forbidden": ("因此被归类为非还原糖。",),
        },
        "高分子化合物的基本概念": {
            "required": ("天然高分子", "合成高分子", "聚合度分布"),
            "forbidden": ("所有合成高分子化合物",),
        },
        "键长及其影响因素": {
            "required": ("共价键", "离子键", "金属键"),
            "forbidden": ("所有共价键，不同键长反映原子大小及成键类型",),
        },
        "苯的物理性质": {
            "required": ("80.1", "5.5", "0.88"),
            "forbidden": (),
        },
        "芳香烃与苯的定义": {
            "required": ("只含碳、氢", "含有一个或多个苯环"),
            "forbidden": (),
        },
        "毒品的危害与社会影响": {
            "required": ("不能用夸张口号", "成瘾"),
            "forbidden": ("其危害甚于洪水猛兽",),
        },
        "元素性质的周期性变化规律": {
            "required": ("总体趋势", "O、F", "稀有气体"),
            "forbidden": ("最高正价=主族序数，最低负价=主族序数-8",),
        },
        "同周期元素主要化合价的周期性变化": {
            "required": ("O、F", "稀有气体", "OF2"),
            "forbidden": ("最高正价=族序数（O、F除外）", "O和F因为座位太抢手"),
        },
        "主族元素最高正化合价与族序数的关系": {
            "required": ("OF2",),
            "forbidden": ("所以没有‘最高正价’这个说法",),
        },
        "蛋白质的空间结构与肽键": {
            "required": ("二硫键", "变性通常不破坏肽键"),
            "forbidden": ("维持该结构的唯一化学键是肽键",),
        },
        "金属腐蚀快慢的比较规律": {
            "required": ("不能脱离具体体系", "固定顺序"),
            "forbidden": ("第五步：总结排序规律", "速度最快且最彻底"),
        },
        "化学键": {
            "required": ("金属键",),
            "forbidden": ("涵盖离子键和共价键两种主要类型",),
        },
        "取代反应": {
            "required": ("不能一律说",),
            "forbidden": ("产物中一定含有无机小分子",),
        },
        "配位键的形成机理": {
            "required": ("不能一概说完全相同",),
            "forbidden": ("在键长、键能、稳定性上完全等同",),
        },
        "铁合金（生铁与钢）的分类及性能": {
            "required": ("不能把含碳量当作唯一判据",),
            "forbidden": ("强调这是分类的唯一依据",),
        },
        "长周期中金属元素的电子结构特征": {
            "required": ("As、Se、Br",),
            "forbidden": ("长周期新增元素均为金属",),
        },
        "蛋白质含量的测定原理": {
            "required": ("胶原蛋白的含氮量通常高于 16%",),
            "forbidden": ("胶原蛋白较低",),
        },
        "燃料电池的特点与优势": {
            "required": ("理论效率不受卡诺循环限制", "统一的“>80%”", "含碳燃料"),
            "forbidden": ("能量转化效率极高（通常>80%）", "实现了低污染或零排放"),
        },
        "电解池的工作原理与离子迁移": {
            "required": ("电子不穿过溶液",),
            "forbidden": ("经电解质溶液离子导电后",),
        },
        "钢铁的析氢腐蚀": {
            "required": ("不能把O2写成该过程的必要反应物",),
            "forbidden": ("反应速率通常较快", "对金属结构的破坏性更直接"),
        },
        "电解池电极反应式的书写": {
            "required": ("绝对放电顺序",),
            "forbidden": ("Ag⁺ > Fe³⁺ > Cu²⁺ > H⁺ > ...）", "阴极：Ag⁺ > Fe³⁺"),
        },
        "纤维素的水解反应": {
            "required": ("较强酸", "n−1"),
            "forbidden": ("稀硫酸或酶催化下", "浓硫酸的催化作用"),
        },
        "原电池原理与构成": {
            "required": ("PbO2", "盐桥或隔膜不是所有原电池的必要条件"),
            "forbidden": (
                "正极材料可能参与反应（如镁铝氢氧化钠原电池）",
                "两个活泼性不同的电极",
            ),
        },
        "乙醇与钠的反应": {
            "required": ("断键位置是O–H键", "不是卤代烃式的亲核取代"),
            "forbidden": ("反应本质是置换反应（或广义取代）",),
        },
        "缩聚反应中的小分子副产物": {
            "required": ("n−1", "2n−1", "并非所有逐步聚合"),
            "forbidden": ("判断是否为缩聚反应的关键依据是",),
        },
        "高分子结构简式的书写规范": {
            "required": ("端基不能套用统一模板", "引发剂残留"),
            "forbidden": ("通常保留引发剂或反应残留的官能团",),
        },
        "缩聚物结构简式书写规范": {
            "required": ("不是固定模板", "不是“引发剂残留”的同义词"),
            "forbidden": ("缩聚物的端基是确定的",),
        },
    }
    for concept_name, expectations in regression_expectations.items():
        concept = concept_by_name.get(concept_name)
        check(concept is not None, f"regression concept missing: {concept_name}")
        if concept is None:
            continue
        text = "\n".join(
            [
                concept["definition"]["statement"],
                concept["definition"]["scope"],
                *concept["definition"]["conditions"],
                *concept["definition"]["exceptions"],
                *concept["definition"]["boundary_notes"],
                *concept["core_ideas"],
                concept["teaching"]["student_explanation"],
                *concept["teaching"]["teaching_sequence"],
                concept["teaching"].get("analogy", {}).get("text", ""),
            ]
        )
        for required in expectations["required"]:
            check(
                required in text,
                f"{concept_name}: regression requirement missing: {required}",
            )
        for forbidden in expectations["forbidden"]:
            check(
                forbidden not in text,
                f"{concept_name}: stale correction remains: {forbidden}",
            )

    hydrogen_corrosion = concept_by_name.get("钢铁的析氢腐蚀")
    check(
        hydrogen_corrosion is not None,
        "regression concept missing: 钢铁的析氢腐蚀",
    )
    if hydrogen_corrosion is not None:
        check(
            "O2" not in hydrogen_corrosion["representations"]["formulas"],
            "钢铁的析氢腐蚀: O2 must not remain in required formulas",
        )

    # Confusable pairs are explicit, symmetric contrast records. They are
    # separate from prerequisite/related edges because their teaching use is
    # "tell these apart", not "learn in this order".
    pair_ids: set[str] = set()
    expected_confusable: dict[str, set[str]] = defaultdict(set)
    for pair in confusable_pairs:
        pair_id = pair["pair_id"]
        check(pair_id not in pair_ids, f"duplicate confusable pair_id: {pair_id}")
        pair_ids.add(pair_id)
        left = pair["left_concept_id"]
        right = pair["right_concept_id"]
        check(left in concept_by_id, f"{pair_id}: missing left concept")
        check(right in concept_by_id, f"{pair_id}: missing right concept")
        check(left != right, f"{pair_id}: self-referential confusable pair")
        check(bool(pair.get("dimensions")), f"{pair_id}: missing comparison dimensions")
        check(bool(pair.get("distinction", "").strip()), f"{pair_id}: missing distinction")
        check(
            pair.get("review_status") == "machine_reviewed",
            f"{pair_id}: unexpected review status",
        )
        check(pair.get("human_verified") is False, f"{pair_id}: must not claim human review")
        check(
            pair.get("evidence_status") == "ai_textbook_summary_unverified",
            f"{pair_id}: unexpected evidence status",
        )
        expected_confusable[left].add(right)
        expected_confusable[right].add(left)

    for concept in concepts:
        actual = set(concept["relations"]["confusable"])
        expected = expected_confusable[concept["concept_id"]]
        check(
            actual == expected,
            f"{concept['concept_id']}: confusable relations differ from contrast table",
        )

    # Aliases are a public lookup surface; they must not be ambiguous.
    canonical_names = {concept["canonical_name"] for concept in concepts}
    alias_owners: dict[str, list[str]] = defaultdict(list)
    for concept in concepts:
        for alias in concept["aliases"]:
            alias_owners[alias].append(concept["concept_id"])
            check(
                alias != concept["canonical_name"],
                f"{concept['concept_id']}: alias equals its canonical name",
            )
            check(
                alias not in canonical_names
                or alias == concept["canonical_name"],
                f"{concept['concept_id']}: alias collides with another canonical name: {alias}",
            )
    for alias, owners in alias_owners.items():
        check(
            len(owners) == 1,
            f"ambiguous retained alias {alias!r} owned by {owners}",
        )

    # The relation table must be a lossless translation of the source relation
    # fields, not a filtered or invented subset.
    relation_expected: Counter[tuple[str, str, str, str]] = Counter()
    kp_to_concept = {
        row["occurrence_id"]: row["concept_id"] for row in occurrences
    }
    relation_fields = {
        "prerequisites": "prerequisites",
        "related": "related_points",
    }
    for book_id in book_ids:
        for record in source_by_book[book_id]:
            for relation_type, source_field in relation_fields.items():
                for label in record.get(source_field, []):
                    relation_expected[
                        (
                            kp_to_concept[record["kp_id"]],
                            record["kp_id"],
                            relation_type,
                            label.strip(),
                        )
                    ] += 1
    relation_actual: Counter[tuple[str, str, str, str]] = Counter()
    relation_ids: set[str] = set()
    relation_counts = Counter()
    targets_by_source: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"prerequisites": set(), "related": set()}
    )
    resolved_relations_by_source: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for relation in relations:
        key = (
            relation["source_concept_id"],
            relation["source_occurrence_id"],
            relation["relation_type"],
            relation["target_label"],
        )
        relation_actual[key] += 1
        check(
            relation["relation_id"] not in relation_ids,
            f"duplicate relation_id: {relation['relation_id']}",
        )
        relation_ids.add(relation["relation_id"])
        check(
            relation["resolution_status"] in RELATION_STATUSES,
            f"invalid relation status: {relation['resolution_status']}",
        )
        check(
            relation["resolution_method"] in RELATION_METHODS,
            f"invalid relation method: {relation['resolution_method']}",
        )
        relation_counts[relation["resolution_status"]] += 1
        target = relation.get("target_concept_id")
        if relation["resolution_status"] == "resolved":
            check(
                target in concept_by_id,
                f"resolved relation points to missing concept: {target}",
            )
            if target in concept_by_id:
                targets_by_source[relation["source_concept_id"]][
                    relation["relation_type"]
                ].add(target)
                resolved_relations_by_source[relation["source_concept_id"]].add(
                    (relation["relation_type"], target)
                )
        elif relation["resolution_status"] == "self_reference":
            check(
                target == relation["source_concept_id"],
                f"self reference target differs from source: {relation['relation_id']}",
            )
        else:
            check(
                target is None,
                f"non-resolved relation has target_concept_id: {relation['relation_id']}",
            )
        if relation["resolution_status"] == "ambiguous":
            check(
                bool(relation.get("target_candidates")),
                f"ambiguous relation has no candidates: {relation['relation_id']}",
            )
        if relation["resolution_status"] == "self_reference":
            check(
                bool(relation.get("target_candidates")) is False,
                f"self reference should not have target candidates: {relation['relation_id']}",
            )
        if relation["resolution_status"] == "external_prior":
            check(
                relation["resolution_method"] == "external_prior",
                f"external prior relation has wrong method: {relation['relation_id']}",
            )
            check(
                bool(relation.get("resolution_note")),
                f"external prior relation lacks a note: {relation['relation_id']}",
            )
    check(
        relation_actual == relation_expected,
        "canonical relation table does not exactly cover source relation fields",
    )
    check(
        len(relations) == sum(relation_expected.values()),
        "canonical relation row count differs from source relation count",
    )
    expected_counts = Counter(
        {
            "resolved": model_manifest["relations"]["resolved"],
            "unresolved": model_manifest["relations"]["unresolved"],
            "ambiguous": model_manifest["relations"]["ambiguous"],
            "self_reference": model_manifest["relations"]["self_reference"],
            "external_prior": model_manifest["relations"]["external_prior"],
        }
    )
    check(
        relation_counts == expected_counts,
        f"manifest relation counts differ: {relation_counts} vs {expected_counts}",
    )

    for concept in concepts:
        for relation_type in ("prerequisites", "related"):
            actual = set(concept["relations"][relation_type])
            expected = targets_by_source[concept["concept_id"]][relation_type]
            check(
                actual == expected,
                f"{concept['concept_id']}: concept {relation_type} differs from relation table",
            )

    # Every unresolved/ambiguous relation must remain visible in the owning
    # concept's review queue.
    issues_by_concept = {
        concept["concept_id"]: concept["quality"]["open_issues"]
        for concept in concepts
    }
    for relation in relations:
        if relation["resolution_status"] in {"unresolved", "ambiguous"}:
            issue = f"unresolved relation: {relation['target_label']}"
            check(
                issue in issues_by_concept[relation["source_concept_id"]],
                f"{relation['source_concept_id']}: missing open issue for {relation['target_label']}",
            )
        if relation["resolution_status"] == "external_prior":
            issue = f"external prior relation: {relation['target_label']}"
            check(
                issue in issues_by_concept[relation["source_concept_id"]],
                f"{relation['source_concept_id']}: missing external-prior issue for {relation['target_label']}",
            )

    queue_ids = {row["concept_id"] for row in review_queue}
    expected_queue_ids = {
        concept["concept_id"]
        for concept in concepts
        if concept["quality"]["open_issues"]
    }
    check(queue_ids == expected_queue_ids, "review-queue coverage mismatch")
    check(
        model_manifest["quality"]["concepts_with_open_issues"]
        == len(review_queue),
        "manifest open-issue concept count mismatch",
    )
    check(
        model_manifest["quality"]["concepts_with_unresolved_relations"]
        == sum(
            1
            for concept in concepts
            if any(
                issue.startswith("unresolved relation:")
                for issue in concept["quality"]["open_issues"]
            )
        ),
        "manifest unresolved-relation concept count mismatch",
    )
    check(
        model_manifest["quality"]["blocking_concepts"]
        == sum(
            1
            for concept in concepts
            if any(
                detail.get("severity") == "blocking"
                for detail in concept["quality"]["issue_details"]
            )
        ),
        "manifest blocking concept count mismatch",
    )
    for row in review_queue:
        expected = concept_by_id[row["concept_id"]]
        check(
            row["issue_details"] == expected["quality"]["issue_details"],
            f"{row['concept_id']}: review queue issue details mismatch",
        )
        check(
            row["issue_codes"]
            == sorted(
                {detail["code"] for detail in expected["quality"]["issue_details"]}
            ),
            f"{row['concept_id']}: review queue issue codes mismatch",
        )
        check(
            row["evidence_status"] == "ai_textbook_summary_unverified",
            f"{row['concept_id']}: review queue evidence status mismatch",
        )

    gap_labels = {row["target_label"] for row in relation_gaps}
    expected_gap_labels = {
        relation["target_label"]
        for relation in relations
        if relation["resolution_status"] != "resolved"
    }
    check(
        gap_labels == expected_gap_labels,
        "relation-gap labels do not exactly cover unresolved, ambiguous, self-referential and external relations",
    )
    gap_counts = Counter()
    for relation in relations:
        if relation["resolution_status"] != "resolved":
            gap_counts[relation["target_label"]] += 1
    for row in relation_gaps:
        check(
            row["relation_count"] == gap_counts[row["target_label"]],
            f"relation-gap count mismatch: {row['target_label']}",
        )
        check(
            row["source_concept_ids"]
            and row["source_occurrence_ids"]
            and row["relation_types"]
            and row["resolution_statuses"],
            f"relation gap lacks source context: {row['target_label']}",
        )

    # P0/P1/P2 overrides must still be present in source and marked on the
    # corresponding canonical concepts.
    override_payloads = []
    for path, label in ((P0_PATH, "P0"), (P1_PATH, "P1"), (P2_PATH, "P2")):
        payload = load_json_config(path)
        override_payloads.append((label, payload["overrides"]))
    for label, overrides in override_payloads:
        for kp_id, values in overrides.items():
            check(kp_id in source_explicit, f"{label}: missing source explicit {kp_id}")
            concept_id = kp_to_concept.get(kp_id)
            check(concept_id in concept_by_id, f"{label}: missing canonical mapping {kp_id}")
            if concept_id in concept_by_id:
                marker = {
                    "P0": "P0 content correction",
                    "P1": "P1 content correction",
                    "P2": "P2 consistency correction",
                }[label]
                check(
                    any(
                        correction.startswith(marker)
                        for correction in concept_by_id[concept_id]["quality"]["corrections"]
                    ),
                    f"{concept_id}: missing {label} correction marker",
                )
            for kind, fields in values.items():
                source = source_explicit if kind == "explicit" else source_teaching
                check(
                    kp_id in source and merge_matches(source[kp_id], fields),
                    f"{label}: override not reflected in {kind}/{kp_id}",
                )

    # Structural validation against the published JSON Schema.
    schema = load_json_config(SCHEMA_PATH)
    confusable_schema = load_json_config(CONFUSABLE_SCHEMA_PATH)
    equation_schema = load_json_config(EQUATION_SCHEMA_PATH)
    locator_schema = load_json_config(LOCATOR_SCHEMA_PATH)
    try:
        import jsonschema
    except Exception:
        if args.strict_schema:
            errors.append("jsonschema is unavailable with --strict-schema")
    else:
        validator = jsonschema.Draft202012Validator(schema)
        for concept in concepts:
            for error in sorted(validator.iter_errors(concept), key=str):
                errors.append(
                    f"schema {concept.get('concept_id', '<unknown>')}: "
                    f"{error.json_path}: {error.message}"
                )
        confusable_validator = jsonschema.Draft202012Validator(confusable_schema)
        for pair in confusable_pairs:
            for error in sorted(confusable_validator.iter_errors(pair), key=str):
                errors.append(
                    f"confusable schema {pair.get('pair_id', '<unknown>')}: "
                    f"{error.json_path}: {error.message}"
                )
        equation_validator = jsonschema.Draft202012Validator(equation_schema)
        for review in equation_reviews:
            for error in sorted(
                equation_validator.iter_errors(review), key=str
            ):
                errors.append(
                    f"equation schema {review.get('review_id', '<unknown>')}: "
                    f"{error.json_path}: {error.message}"
                )
        locator_validator = jsonschema.Draft202012Validator(locator_schema)
        for locator in textbook_locators:
            for error in sorted(
                locator_validator.iter_errors(locator), key=str
            ):
                errors.append(
                    f"locator schema {locator.get('locator_id', '<unknown>')}: "
                    f"{error.json_path}: {error.message}"
                )

    # Keep machine extraction visible instead of presenting it as verified
    # chemistry. No formula/equation is certified by this validator.
    check(
        model_manifest["quality"]["formula_validation"] == "not_performed",
        "formula validation status must not claim verification",
    )
    check(
        model_manifest["quality"]["equation_validation"]
        == "partial_machine_mass_charge_and_structural_review",
        "equation validation status must remain partial and qualified",
    )
    check(
        model_manifest["human_verified"] is False,
        "canonical model must not claim human verification",
    )
    check(
        model_manifest["equation_review"]["textbook_evidence_status"]
        == "unverified_ai_summary_pages_only",
        "equation review must preserve unverified textbook evidence status",
    )

    summary = {
        "concepts": len(concepts),
        "occurrences": len(occurrences),
        "relations": dict(relation_counts),
        "review_queue": len(review_queue),
        "equation_reviews": len(equation_reviews),
        "textbook_locators": len(textbook_locators),
        "errors": len(errors),
        "warnings": len(warnings),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")
    if errors:
        print("\nErrors:")
        for error in errors[:200]:
            print(f"- {error}")
        if len(errors) > 200:
            print(f"- ... {len(errors) - 200} more")
        return 1
    print("Canonical model validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
