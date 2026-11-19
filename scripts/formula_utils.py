#!/usr/bin/env python3
"""Conservative classification and display helpers for chemistry formulas."""

from __future__ import annotations

import re


ELEMENTS = set(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co "
    "Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb "
    "Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re "
    "Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es "
    "Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split()
)
PLACEHOLDER_RE = re.compile(r"^\{\{[A-Za-z0-9_]+\}\}$")
POLYMER_FORMULA_RE = re.compile(
    r"^(\([A-Z][A-Za-z0-9]*\))([nm])$"
)
GENERIC_FORMULA_RE = re.compile(
    r"^C[nm]H(?:[0-9nm]+)(?:[+\-][0-9]+)?(?:O[0-9nm]*)?$"
)
CHARGE_SUFFIX_RE = re.compile(r"^(.*?)(\d*)([+\-])$")
CONDENSED_FORMULAS = {
    "HCOOH",
    "CH3OH",
    "CH3Cl",
    "CH2Cl2",
    "CHCl3",
    "CH3CHO",
    "CH3COOH",
    "CH3COONa",
    "CH3COONH4",
    "CH3COCH3",
    "CH3OCOOCH3",
    "CH3CH2OH",
    "C2H5OH",
    "C6H5OH",
    "C6H5ONa",
    "C6H5Br",
}
SUBSCRIPT_DIGITS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
SUPERSCRIPT_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def classify_formula(formula: str) -> str:
    """Classify a formula without claiming a unique chemical interpretation."""
    value = formula.strip()
    if PLACEHOLDER_RE.fullmatch(value):
        return "protected_placeholder"
    if value == "HIn":
        return "indicator_generic"
    if POLYMER_FORMULA_RE.fullmatch(value):
        return "polymer_formula"
    if GENERIC_FORMULA_RE.fullmatch(value):
        return "generic_formula"
    if CHARGE_SUFFIX_RE.fullmatch(value):
        return "ion_formula"
    if value in ELEMENTS:
        return "element_symbol"
    if value in CONDENSED_FORMULAS:
        return "condensed_formula"
    return "molecular_formula"


def formula_syntax_errors(formula: str) -> list[str]:
    """Return syntax errors, not a judgement that the substance exists."""
    value = formula.strip()
    kind = classify_formula(value)
    if kind in {
        "protected_placeholder",
        "indicator_generic",
        "generic_formula",
        "polymer_formula",
    }:
        return []

    core = value
    if kind == "ion_formula":
        match = CHARGE_SUFFIX_RE.fullmatch(value)
        if not match:
            return [f"invalid ion charge suffix: {value}"]
        core = match.group(1)
        if not core:
            return [f"ion charge has no formula: {value}"]

    tokens = re.findall(r"[A-Z][a-z]?|[()]|\d+", core)
    if "".join(tokens) != core:
        return [f"unsupported formula syntax: {value}"]

    errors: list[str] = []
    depth = 0
    can_multiply = False
    for token in tokens:
        if token == "(":
            depth += 1
            can_multiply = False
            continue
        if token == ")":
            if depth == 0:
                errors.append(f"unexpected closing parenthesis in {value}")
            depth = max(0, depth - 1)
            can_multiply = True
            continue
        if token.isdigit():
            if not can_multiply:
                errors.append(f"unexpected multiplier in {value}")
            can_multiply = False
            continue
        if token not in ELEMENTS:
            errors.append(f"unknown element symbol {token} in {value}")
        can_multiply = True
    if depth:
        errors.append(f"unclosed parenthesis in {value}")
    return errors


def display_formula(formula: str) -> str:
    """Create a readable formula while preserving protected placeholders."""
    value = formula.strip()
    if PLACEHOLDER_RE.fullmatch(value):
        return value
    kind = classify_formula(value)
    if kind == "indicator_generic":
        return value
    if kind in {"polymer_formula", "generic_formula"}:
        return (
            value.replace("n", "ₙ")
            .replace("m", "ₘ")
            .translate(SUBSCRIPT_DIGITS)
            .replace("+", "₊")
            .replace("-", "₋")
        )
    if kind == "ion_formula":
        match = CHARGE_SUFFIX_RE.fullmatch(value)
        if match:
            body, magnitude, sign = match.groups()
            charge = magnitude if magnitude not in {"", "1"} else ""
            superscript = charge.translate(SUPERSCRIPT_DIGITS)
            superscript += "⁺" if sign == "+" else "⁻"
            return body.translate(SUBSCRIPT_DIGITS) + superscript
    return value.translate(SUBSCRIPT_DIGITS)
