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


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CANONICAL_DIR = DATA_DIR / "canonical"
SCHEMA_PATH = DATA_DIR / "schema" / "chem-concept-v1.schema.json"
CONFUSABLE_SCHEMA_PATH = DATA_DIR / "schema" / "chem-confusable-pair-v1.schema.json"
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

    # Keep machine extraction visible instead of presenting it as verified
    # chemistry. No formula/equation is certified by this validator.
    check(
        model_manifest["quality"]["formula_validation"] == "not_performed",
        "formula validation status must not claim verification",
    )
    check(
        model_manifest["quality"]["equation_validation"] == "not_performed",
        "equation validation status must not claim verification",
    )
    check(
        model_manifest["human_verified"] is False,
        "canonical model must not claim human verification",
    )

    summary = {
        "concepts": len(concepts),
        "occurrences": len(occurrences),
        "relations": dict(relation_counts),
        "review_queue": len(review_queue),
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
