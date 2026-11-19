#!/usr/bin/env python3
"""Normalize textbook hierarchy metadata and make knowledge-point IDs unique."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

BOOK_ROOTS = {
    "tb_bx1": "必修第一册",
    "tb_bx2": "必修第二册",
    "tb_xx1": "化学反应原理",
    "tb_xx2": "物质结构与性质",
    "tb_xx3": "有机化学基础",
}

CHAPTER_OVERRIDES = {
    ("tb_xx3", "第二章"): "第二章 烃",
    ("tb_xx3", "第二章 思考与讨论"): "第二章 烃",
    ("tb_xx3", "第二章 科学·技术·社会"): "第二章 烃",
}

SECTION_OVERRIDES = {
    ("tb_xx1", "第一章 化学反应的热效应", "第二节"): "第二节 反应热的计算",
}

APPENDIX_CHAPTER = "附录"
APPENDIX_SECTIONS = {
    "附录Ⅰ": "附录Ⅰ 实验室安全与事故应急处理",
    "附录Ⅱ": "附录Ⅱ GHS化学品安全标识",
}

TRAILING_PAGE_NUMBER = re.compile(r"(?<=[^\d])\s*\d+\s*$")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def format_jsonl(records: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def normalize_section(section: str) -> str:
    return TRAILING_PAGE_NUMBER.sub("", section).strip()


def normalize_chapter(book_id: str, chapter: str) -> str:
    return CHAPTER_OVERRIDES.get((book_id, chapter), chapter)


def normalize_ref(
    book_id: str,
    ref: dict[str, Any],
    category_path: list[str],
    kp_name: str,
) -> tuple[dict[str, Any], list[str]]:
    normalized = dict(ref)
    chapter = normalize_chapter(book_id, str(normalized.get("chapter", "")).strip())
    section = normalize_section(str(normalized.get("section", "")))
    section = SECTION_OVERRIDES.get((book_id, chapter, section), section)

    appendix = category_path[2] if len(category_path) > 2 else ""
    if book_id == "tb_bx1" and appendix in APPENDIX_SECTIONS and "化学键" in section:
        chapter = APPENDIX_CHAPTER
        section = APPENDIX_SECTIONS[appendix]

    normalized["chapter"] = chapter
    normalized["section"] = section

    normalized_category_path = list(category_path)
    if len(normalized_category_path) < 3:
        raise ValueError(f"{book_id} {kp_name}: category_path has fewer than 3 levels")
    normalized_category_path[0] = BOOK_ROOTS[book_id]
    normalized_category_path[1] = chapter
    if chapter == APPENDIX_CHAPTER:
        normalized_category_path[2] = section

    return normalized, normalized_category_path


def stable_record_id(book_id: str, old_id: str, name: str) -> str:
    seed = json.dumps(
        ["hs-chemistry-tutor", "kp-id-v1", book_id, old_id, name],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "kp_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def normalize_explicit(book_id: str, records: list[dict[str, Any]]) -> dict[str, int]:
    counts = defaultdict(int)
    for record in records:
        refs = record.get("textbook_refs") or []
        category_path = record.get("category_path") or []
        normalized_refs = []
        normalized_path = category_path
        for ref in refs:
            normalized_ref, candidate_path = normalize_ref(
                book_id, ref, category_path, record.get("name", "")
            )
            if normalized_ref != ref:
                counts["refs"] += 1
                if normalized_ref.get("chapter") != ref.get("chapter"):
                    counts["chapters"] += 1
                if normalized_ref.get("section") != ref.get("section"):
                    counts["sections"] += 1
            normalized_refs.append(normalized_ref)
            normalized_path = candidate_path

        if normalized_refs and len({ref.get("chapter") for ref in normalized_refs}) > 1:
            raise ValueError(
                f"{book_id} {record.get('kp_id')}: refs use multiple chapters"
            )

        record["textbook_refs"] = normalized_refs
        if normalized_path != category_path:
            record["category_path"] = normalized_path
            counts["category_paths"] += 1
    return counts


def rename_duplicate_ids(
    explicit_by_book: dict[str, list[dict[str, Any]]],
) -> dict[tuple[str, str], str]:
    owners: dict[str, str] = {}
    all_ids = {
        record["kp_id"]
        for records in explicit_by_book.values()
        for record in records
    }
    renames: dict[tuple[str, str], str] = {}

    for book_id in sorted(explicit_by_book):
        for record in explicit_by_book[book_id]:
            old_id = record["kp_id"]
            owner = owners.get(old_id)
            if owner is None:
                owners[old_id] = book_id
                continue
            if owner == book_id:
                raise ValueError(f"{book_id}: duplicate kp_id {old_id} within a book")

            new_id = stable_record_id(book_id, old_id, record.get("name", ""))
            while new_id in all_ids or new_id in owners:
                new_id = "kp_" + hashlib.sha256(
                    f"{new_id}|collision".encode("utf-8")
                ).hexdigest()[:12]
            all_ids.add(new_id)
            owners[new_id] = book_id
            renames[(book_id, old_id)] = new_id
            record["kp_id"] = new_id

    return renames


def apply_explicit_metadata_to_teaching(
    book_id: str,
    records: list[dict[str, Any]],
    renames: dict[tuple[str, str], str],
    canonical_refs: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[int, int]:
    renamed = 0
    refs_updated = 0
    for record in records:
        if record.get("kp_id") != record.get("source_kp_id"):
            raise ValueError(
                f"{book_id} {record.get('kp_id')}: kp_id and source_kp_id differ"
            )
        old_id = record["source_kp_id"]
        new_id = renames.get((book_id, old_id), old_id)
        if new_id != old_id:
            record["kp_id"] = new_id
            record["source_kp_id"] = new_id
            renamed += 1

        canonical = canonical_refs.get((book_id, new_id))
        if canonical is None:
            raise ValueError(f"{book_id} {new_id}: missing explicit textbook_refs")
        teaching_refs = record.get("textbook_refs") or []
        if len(teaching_refs) != len(canonical):
            raise ValueError(f"{book_id} {new_id}: textbook_refs length mismatch")
        normalized_teaching_refs = []
        for teaching_ref, explicit_ref in zip(teaching_refs, canonical):
            normalized_ref = dict(teaching_ref)
            for key in ("book_id", "book_title", "chapter", "section", "pages"):
                normalized_ref[key] = explicit_ref.get(key)
            normalized_teaching_refs.append(normalized_ref)
        if normalized_teaching_refs != teaching_refs:
            record["textbook_refs"] = normalized_teaching_refs
            refs_updated += 1
    return renamed, refs_updated


def validate(
    manifest: dict[str, Any],
    explicit_by_book: dict[str, list[dict[str, Any]]],
    teaching_by_book: dict[str, list[dict[str, Any]]],
) -> None:
    expected_books = {book["book_id"]: book for book in manifest.get("books", [])}
    if set(explicit_by_book) != set(expected_books):
        raise ValueError("Explicit data books do not match manifest")
    if set(teaching_by_book) != set(expected_books):
        raise ValueError("Teaching data books do not match manifest")

    all_ids: list[str] = []
    for book_id, expected in expected_books.items():
        explicit = explicit_by_book[book_id]
        teaching = teaching_by_book[book_id]
        if len(explicit) != expected["kp_count"]:
            raise ValueError(f"{book_id}: explicit count differs from manifest")
        if len(teaching) != expected["teaching_count"]:
            raise ValueError(f"{book_id}: teaching count differs from manifest")

        explicit_by_id = {record["kp_id"]: record for record in explicit}
        teaching_by_id = {record["kp_id"]: record for record in teaching}
        if set(explicit_by_id) != set(teaching_by_id):
            raise ValueError(f"{book_id}: explicit and teaching IDs differ")

        for kp_id, record in explicit_by_id.items():
            all_ids.append(kp_id)
            category_path = record.get("category_path") or []
            refs = record.get("textbook_refs") or []
            if not refs:
                raise ValueError(f"{book_id} {kp_id}: missing textbook_refs")
            if len(category_path) < 3:
                raise ValueError(f"{book_id} {kp_id}: invalid category_path")
            if category_path[0] != BOOK_ROOTS[book_id]:
                raise ValueError(f"{book_id} {kp_id}: invalid category root")
            if category_path[1] != refs[0].get("chapter"):
                raise ValueError(f"{book_id} {kp_id}: category chapter mismatch")

            for ref in refs:
                section = str(ref.get("section", "")).strip()
                chapter = str(ref.get("chapter", "")).strip()
                if not section or TRAILING_PAGE_NUMBER.search(section):
                    raise ValueError(f"{book_id} {kp_id}: invalid section {section!r}")
                if section == "第二节":
                    raise ValueError(f"{book_id} {kp_id}: section title is missing")
                if chapter != APPENDIX_CHAPTER:
                    if not re.match(r"^第[一二三四五六七八九十]+章\s+\S+", chapter):
                        raise ValueError(f"{book_id} {kp_id}: invalid chapter {chapter!r}")

            teaching_record = teaching_by_id[kp_id]
            if teaching_record.get("source_kp_id") != kp_id:
                raise ValueError(f"{book_id} {kp_id}: source_kp_id mismatch")
            if teaching_record.get("name") != record.get("name"):
                raise ValueError(f"{book_id} {kp_id}: name mismatch")
            teaching_refs = teaching_record.get("textbook_refs") or []
            if len(teaching_refs) != len(refs):
                raise ValueError(f"{book_id} {kp_id}: textbook_refs length mismatch")
            for teaching_ref, explicit_ref in zip(teaching_refs, refs):
                for key in ("book_id", "book_title", "chapter", "section", "pages"):
                    if teaching_ref.get(key) != explicit_ref.get(key):
                        raise ValueError(
                            f"{book_id} {kp_id}: textbook_refs {key} mismatch"
                        )

    if len(all_ids) != len(set(all_ids)):
        raise ValueError("kp_id is not globally unique")

    for book_id in sorted(explicit_by_book):
        chapters = defaultdict(set)
        for record in explicit_by_book[book_id]:
            for ref in record["textbook_refs"]:
                chapters[ref["chapter"]].add(ref["section"])
        summary = ", ".join(
            f"{chapter}={len(sections)}" for chapter, sections in sorted(chapters.items())
        )
        print(f"{book_id}: {len(chapters)} chapters, {sum(map(len, chapters.values()))} sections | {summary}")


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
        help="Write normalized data. Without this flag, only report planned changes.",
    )
    args = parser.parse_args()

    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    book_ids = [book["book_id"] for book in manifest["books"]]
    explicit_by_book = {
        book_id: read_jsonl(DATA_DIR / "explicit" / f"{book_id}.explicit.jsonl")
        for book_id in book_ids
    }
    teaching_by_book = {
        book_id: read_jsonl(DATA_DIR / "teaching" / f"{book_id}.teaching.jsonl")
        for book_id in book_ids
    }

    total_counts = defaultdict(int)
    for book_id, records in explicit_by_book.items():
        for key, value in normalize_explicit(book_id, records).items():
            total_counts[key] += value

    renames = rename_duplicate_ids(explicit_by_book)
    canonical_refs = {
        (book_id, record["kp_id"]): record["textbook_refs"]
        for book_id, records in explicit_by_book.items()
        for record in records
    }
    renamed_teaching = 0
    teaching_refs_updated = 0
    for book_id, records in teaching_by_book.items():
        renamed, refs_updated = apply_explicit_metadata_to_teaching(
            book_id, records, renames, canonical_refs
        )
        renamed_teaching += renamed
        teaching_refs_updated += refs_updated

    print("Planned changes:")
    for key in ("refs", "chapters", "sections", "category_paths"):
        print(f"  {key}: {total_counts[key]}")
    print(f"  explicit kp_id renames: {len(renames)}")
    print(f"  teaching kp_id renames: {renamed_teaching}")
    print(f"  teaching textbook_refs updates: {teaching_refs_updated}")
    for (book_id, old_id), new_id in sorted(renames.items()):
        print(f"  {book_id}: {old_id} -> {new_id}")

    validate(manifest, explicit_by_book, teaching_by_book)

    if args.write:
        changed = []
        for book_id in book_ids:
            explicit_path = DATA_DIR / "explicit" / f"{book_id}.explicit.jsonl"
            teaching_path = DATA_DIR / "teaching" / f"{book_id}.teaching.jsonl"
            if write_if_changed(explicit_path, explicit_by_book[book_id]):
                changed.append(str(explicit_path.relative_to(ROOT)))
            if write_if_changed(teaching_path, teaching_by_book[book_id]):
                changed.append(str(teaching_path.relative_to(ROOT)))
        print(f"Wrote {len(changed)} files:")
        for path in changed:
            print(f"  {path}")
    else:
        print("Dry run only; pass --write to update files.")


if __name__ == "__main__":
    main()
