#!/usr/bin/env python3
"""Recalibrate teaching needs_formula_review flags from focused formula evidence.

An explicit knowledge point's formula-review flag is treated as the authoritative
seed. A teaching record also keeps or receives the flag when its own title or
core explanation has strong formula content:

- the title contains a chemical formula or formula-specific terminology;
- the core explanation contains a reaction arrow together with a formula;
- the title/core explanation contains at least two distinct chemical formulas;
- the title/core explanation uses thermodynamic or equilibrium notation
  such as delta H, Ksp, Ka, Kw, pH, or m/z.

Incidental formula mentions in examples, exercises, or practice hints do not by
themselves trigger the flag.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

ELEMENTS = set(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co "
    "Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb "
    "Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re "
    "Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es "
    "Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split()
)

ACRONYMS = {
    "ABS",
    "ATP",
    "BOD",
    "COD",
    "DDT",
    "DNA",
    "GHS",
    "HDPE",
    "IR",
    "LDPE",
    "MS",
    "NMR",
    "PET",
    "PHB",
    "PMMA",
    "PTFE",
    "PVC",
    "RNA",
    "SAP",
    "STS",
    "TNT",
}

SUBSCRIPT_TRANSLATION = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
SUPERSCRIPT_TRANSLATION = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")

FORMULA_RE = re.compile(
    r"(?<![A-Za-z])((?:\([A-Z][a-z]?\d*\)|[A-Z][a-z]?\d*)+)(?![A-Za-z])"
)
REACTION_ARROW_RE = re.compile(r"(?:→|⇌|⟶|->|<=>)")
FORMULA_TERM_RE = re.compile(
    r"化学式|化学方程式|离子方程式|电离方程式|热化学|电子式|结构式|结构简式|"
    r"化学用语|配平|电极反应|反应式|离子反应|沉淀反应|水解反应|实验式|分子式|"
    r"最简式|相对分子质量"
)
SPECIAL_FORMULA_RE = re.compile(
    r"Δ[HSG]|(?<![A-Za-z])K(?:sp|a|b|w|c)(?![A-Za-z])|"
    r"(?<![A-Za-z])pH(?![A-Za-z])|(?<![A-Za-z])m/z(?![A-Za-z])|离子积|浓度商|平衡常数|"
    r"溶度积|电离常数|水解常数"
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def format_jsonl(records: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def is_valid_formula(token: str) -> bool:
    if token in ACRONYMS:
        return False
    elements = re.findall(r"[A-Z][a-z]?", token)
    if not elements or any(element not in ELEMENTS for element in elements):
        return False
    return len(token) >= 2 and (
        len(elements) >= 2 or any(char.isdigit() for char in token) or "(" in token
    )


def formulas(text: str) -> set[str]:
    normalized = text.translate(SUBSCRIPT_TRANSLATION).translate(
        SUPERSCRIPT_TRANSLATION
    )
    return {
        match.group(1)
        for match in FORMULA_RE.finditer(normalized)
        if is_valid_formula(match.group(1))
    }


def formula_reasons(record: dict[str, Any]) -> set[str]:
    name = record.get("name", "")
    explanation = record.get("teacher_explanation", {})
    core = explanation.get("core_explanation", "") if isinstance(explanation, dict) else ""
    combined = f"{name}\n{core}"
    combined_formulas = formulas(combined)

    reasons = set()
    if formulas(name):
        reasons.add("title_formula")
    if FORMULA_TERM_RE.search(name):
        reasons.add("title_formula_term")
    if REACTION_ARROW_RE.search(core) and combined_formulas:
        reasons.add("core_equation")
    if len(combined_formulas) >= 2:
        reasons.add("multiple_formulas")
    if SPECIAL_FORMULA_RE.search(combined):
        reasons.add("formula_notation")
    if "needs_equation_review" in record.get("quality_flags", []):
        reasons.add("equation_review")
    return reasons


def normalize_order(flags: set[str], canonical_order: list[str]) -> list[str]:
    order = {flag: index for index, flag in enumerate(canonical_order)}
    return sorted(flags, key=lambda flag: order[flag])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write recalibrated flags. Without this flag, only report planned changes.",
    )
    args = parser.parse_args()

    taxonomy = json.loads(
        (ROOT / "scripts" / "quality_flag_taxonomy.json").read_text(encoding="utf-8")
    )
    canonical_order = taxonomy["canonical_order"]
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    book_ids = [book["book_id"] for book in manifest["books"]]

    source_flags: dict[tuple[str, str], bool] = {}
    teaching_by_book: dict[str, list[dict[str, Any]]] = {}
    for book_id in book_ids:
        explicit = read_jsonl(DATA_DIR / "explicit" / f"{book_id}.explicit.jsonl")
        source_flags.update(
            {
                (book_id, record["kp_id"]): "needs_formula_review"
                in record.get("quality_flags", [])
                for record in explicit
            }
        )
        teaching_by_book[book_id] = read_jsonl(
            DATA_DIR / "teaching" / f"{book_id}.teaching.jsonl"
        )

    reason_counts = Counter()
    changed_by_book = Counter()
    added = removed = kept = 0
    for book_id, records in teaching_by_book.items():
        for record in records:
            current = set(record.get("quality_flags", []))
            reasons = formula_reasons(record)
            source_flagged = source_flags[(book_id, record["kp_id"])]
            if source_flagged:
                reasons.add("explicit_seed")
            reason_counts.update(reasons)

            should_flag = bool(reasons)
            had_flag = "needs_formula_review" in current
            if should_flag:
                current.add("needs_formula_review")
            else:
                current.discard("needs_formula_review")
            normalized = normalize_order(current, canonical_order)
            if normalized != record.get("quality_flags", []):
                record["quality_flags"] = normalized
                changed_by_book[book_id] += 1
            if should_flag and not had_flag:
                added += 1
            elif not should_flag and had_flag:
                removed += 1
            elif should_flag and had_flag:
                kept += 1

    allowed = set(canonical_order)
    for book_id, records in teaching_by_book.items():
        for record in records:
            flags = record.get("quality_flags", [])
            if len(flags) != len(set(flags)):
                raise ValueError(f"{book_id} {record.get('kp_id')}: duplicate flags")
            unknown = set(flags) - allowed
            if unknown:
                raise ValueError(
                    f"{book_id} {record.get('kp_id')}: unknown flags {sorted(unknown)}"
                )

    print(f"Teaching formula flags: kept={kept}, removed={removed}, added={added}")
    print("Changed records:")
    for book_id in book_ids:
        print(f"  {book_id}: {changed_by_book[book_id]}")
    print("Retention reasons:")
    for reason, count in reason_counts.most_common():
        print(f"  {reason}: {count}")

    if args.write:
        changed_files = []
        for book_id in book_ids:
            path = DATA_DIR / "teaching" / f"{book_id}.teaching.jsonl"
            output = format_jsonl(teaching_by_book[book_id])
            if output != path.read_text(encoding="utf-8"):
                path.write_text(output, encoding="utf-8")
                changed_files.append(str(path.relative_to(ROOT)))
        print(f"Wrote {len(changed_files)} files:")
        for path in changed_files:
            print(f"  {path}")
    else:
        print("Dry run only; pass --write to update files.")


if __name__ == "__main__":
    main()
