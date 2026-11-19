#!/usr/bin/env python3
"""Conservative parser and mass/charge checker for reviewed equations."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction


ARROW_PATTERN = re.compile(r"\s*(?:->|=>|⇌|⟶|→)\s*")
STATE_SUFFIX_PATTERN = re.compile(
    r"\((?:s|l|g|aq|am|melt|org|solid|liquid|gas|aqueous)\)$"
)
COEFFICIENT_PATTERN = re.compile(r"^(\d+(?:/\d+)?)\s*")
CHARGE_SUFFIX_PATTERN = re.compile(r"\^(\d*)([+-])$")
ELEMENT_OR_GROUP_PATTERN = re.compile(r"[A-Z][a-z]?|\d+|[()[\]]")


class EquationParseError(ValueError):
    """Raised when an equation uses syntax outside the conservative parser."""


@dataclass(frozen=True)
class SideBalance:
    atoms: Counter[str]
    charge: Fraction
    electron_count: Fraction


@dataclass(frozen=True)
class BalanceResult:
    mass_balanced: bool
    charge_balanced: bool
    left: SideBalance
    right: SideBalance


def _parse_number(value: str) -> Fraction:
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise EquationParseError(f"invalid stoichiometric number: {value!r}") from exc


def _split_terms(side: str) -> list[str]:
    terms = [term.strip() for term in re.split(r"\s+\+\s+", side)]
    if not terms or any(not term for term in terms):
        raise EquationParseError(f"invalid side expression: {side!r}")
    return terms


def _parse_charge_and_formula(token: str) -> tuple[str, Fraction]:
    if token in {"e", "e-", "e^-"}:
        return "e", Fraction(-1)
    if token.startswith("e^"):
        suffix = token[1:]
        match = CHARGE_SUFFIX_PATTERN.fullmatch(suffix)
        if match and match.group(2) == "-" and (not match.group(1) or match.group(1) == "1"):
            return "e", Fraction(-1)
    match = CHARGE_SUFFIX_PATTERN.search(token)
    if not match:
        return token, Fraction(0)
    magnitude = _parse_number(match.group(1) or "1")
    charge = magnitude if match.group(2) == "+" else -magnitude
    return token[: match.start()], charge


def _parse_formula_atoms(formula: str) -> Counter[str]:
    if not formula:
        raise EquationParseError("empty formula")
    tokens = ELEMENT_OR_GROUP_PATTERN.findall(formula)
    compact_formula = re.sub(r"\s+", "", formula)
    if "".join(tokens) != compact_formula:
        raise EquationParseError(f"unsupported formula syntax: {formula!r}")

    position = 0

    def parse_sequence(expected_closer: str | None = None) -> Counter[str]:
        nonlocal position
        atoms: Counter[str] = Counter()
        while position < len(tokens):
            token = tokens[position]
            if token in {")", "]"}:
                if expected_closer != token:
                    raise EquationParseError(
                        f"unexpected closing bracket {token!r} in {formula!r}"
                    )
                position += 1
                return atoms
            if token in {"(", "["}:
                expected = ")" if token == "(" else "]"
                position += 1
                group_atoms = parse_sequence(expected)
                multiplier = _read_multiplier(tokens)
                for element, count in group_atoms.items():
                    atoms[element] += count * multiplier
                continue
            if re.fullmatch(r"\d+", token):
                raise EquationParseError(
                    f"unexpected multiplier {token!r} in {formula!r}"
                )
            if not re.fullmatch(r"[A-Z][a-z]?", token):
                raise EquationParseError(
                    f"unexpected token {token!r} in {formula!r}"
                )
            position += 1
            multiplier = _read_multiplier(tokens)
            atoms[token] += multiplier
        if expected_closer is not None:
            raise EquationParseError(
                f"missing closing bracket {expected_closer!r} in {formula!r}"
            )
        return atoms

    def _read_multiplier(token_list: list[str]) -> int:
        nonlocal position
        if position < len(token_list) and re.fullmatch(r"\d+", token_list[position]):
            value = int(token_list[position])
            position += 1
            return value
        return 1

    atoms = parse_sequence()
    if position != len(tokens):
        raise EquationParseError(f"trailing tokens in formula: {formula!r}")
    return atoms


def _parse_side(side: str) -> SideBalance:
    atoms: Counter[str] = Counter()
    charge = Fraction(0)
    electron_count = Fraction(0)
    for raw_term in _split_terms(side):
        term = raw_term.strip()
        state_match = STATE_SUFFIX_PATTERN.search(term)
        if state_match:
            term = term[: state_match.start()].strip()
        coefficient_match = COEFFICIENT_PATTERN.match(term)
        coefficient = Fraction(1)
        if coefficient_match:
            coefficient = _parse_number(coefficient_match.group(1))
            term = term[coefficient_match.end() :].strip()
        if not term:
            raise EquationParseError(f"species missing after coefficient: {raw_term!r}")
        formula, species_charge = _parse_charge_and_formula(term)
        if formula == "e":
            electron_count += coefficient
        else:
            species_atoms = _parse_formula_atoms(formula)
            for element, count in species_atoms.items():
                atoms[element] += coefficient * count
        charge += coefficient * species_charge
    return SideBalance(atoms=atoms, charge=charge, electron_count=electron_count)


def check_balance(equation: str) -> BalanceResult:
    """Return mass and charge balance for a conservative ASCII equation."""
    parts = ARROW_PATTERN.split(equation)
    if len(parts) != 2 or any(not part.strip() for part in parts):
        raise EquationParseError(
            "equation must contain exactly one arrow with species on both sides"
        )
    left = _parse_side(parts[0])
    right = _parse_side(parts[1])
    return BalanceResult(
        mass_balanced=left.atoms == right.atoms,
        charge_balanced=left.charge == right.charge,
        left=left,
        right=right,
    )


def format_balance_error(equation: str, result: BalanceResult) -> str:
    differences = []
    for element in sorted(set(result.left.atoms) | set(result.right.atoms)):
        left_count = result.left.atoms[element]
        right_count = result.right.atoms[element]
        if left_count != right_count:
            differences.append(f"{element}: {left_count} -> {right_count}")
    if result.left.charge != result.right.charge:
        differences.append(
            f"charge: {result.left.charge} -> {result.right.charge}"
        )
    return f"{equation}: " + "; ".join(differences)

