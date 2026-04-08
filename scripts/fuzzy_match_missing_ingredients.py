#!/usr/bin/env python3
"""Propose USDA matches for unmapped recipe ingredients using RapidFuzz.

This script is intentionally read-only with respect to curated mapping files.
It reads:
- `usable/missing_mappings_from_unique_sources.csv`
- `usable/usda/ingredients.csv`

It writes reviewable outputs only:
- `usable/usda/fuzzy_recipe_matches.csv`
- `usable/usda/fuzzy_recipe_rejections.csv`

Matching rule:
- use RapidFuzz fuzzy matching
- accept only scores strictly greater than 85
- default implementation uses `score_cutoff=86` to enforce that rule
"""

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
from rapidfuzz import fuzz


BASE_DIR = Path(__file__).resolve().parents[1]
USABLE_DIR = BASE_DIR / "usable"
USDA_DIR = USABLE_DIR / "usda"
MISSING_PATH = USABLE_DIR / "missing_mappings_from_unique_sources.csv"
MAPPING_FINAL_PATH = USABLE_DIR / "ingredient_mapping_final.csv"
USDA_INGREDIENTS_PATH = USDA_DIR / "ingredients.csv"
MATCHES_OUTPUT_PATH = USDA_DIR / "fuzzy_recipe_matches.csv"
REJECTIONS_OUTPUT_PATH = USDA_DIR / "fuzzy_recipe_rejections.csv"

# These are common words that make ingredient names longer without changing the core food name.
# We remove them only for matching, not for output.
STOPWORDS = {
    "and",
    "or",
    "of",
    "the",
    "with",
    "without",
    "raw",
    "whole",
    "fresh",
    "dry",
    "cooked",
    "boiled",
    "fried",
    "roasted",
    "ground",
    "powder",
    "powders",
    "paste",
    "pulp",
    "juice",
    "slices",
    "slice",
    "chopped",
    "pieces",
    "piece",
    "big",
    "small",
    "medium",
    "green",
    "red",
    "black",
    "white",
    "brown",
    "ripe",
    "tender",
    "rawwhole",
    "slice",
    "sliced",
    "grounded",
}


@dataclass(frozen=True)
class MatchResult:
    source_normalized: str
    source_original: str
    matched_food_code: str
    matched_food_name: str
    score: float
    scorer: str


@dataclass(frozen=True)
class RejectionResult:
    source_normalized: str
    source_original: str
    best_food_code: str
    best_food_name: str
    best_score: float
    reason: str


def normalize_text(value: object) -> str:
    """Normalize text for fuzzy matching.

    We keep the output human-readable, but make matching more robust by:
    - applying unicode normalization
    - lowercasing
    - stripping quotes
    - collapsing punctuation into spaces
    - collapsing repeated whitespace
    """

    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\xa0", " ")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize_for_matching(value: object) -> str:
    """Turn ingredient text into a token string optimized for fuzzy comparison."""

    tokens: list[str] = []
    for token in normalize_text(value).split():
        if token in STOPWORDS:
            continue
        if token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        elif token.endswith("s") and len(token) > 3:
            token = token[:-1]
        tokens.append(token)
    return " ".join(tokens)


def split_originals(raw_value: str) -> list[str]:
    """Split a cell that may contain multiple original spellings separated by `|`."""

    if not raw_value:
        return []
    parts = [part.strip() for part in str(raw_value).split("|")]
    return [part for part in parts if part]


def load_existing_mapping_foods(mapping_path: Path) -> set[str]:
    """Load already mapped food ingredients so we do not re-suggest them."""

    mapped: set[str] = set()
    if not mapping_path.exists():
        return mapped

    with mapping_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return mapped
        if "food_ingredient" not in reader.fieldnames:
            f.seek(0)
            fallback = csv.reader(f)
            next(fallback, None)
            for row in fallback:
                if row:
                    mapped.add(normalize_text(row[0]))
            return mapped

        for row in reader:
            raw = row.get("food_ingredient") or ""
            norm = normalize_text(raw)
            if norm:
                mapped.add(norm)

    return mapped


def load_missing_sources(missing_path: Path) -> list[dict[str, str]]:
    """Load rows from the missing-mappings CSV and keep recipe-origin rows only."""

    if not missing_path.exists():
        raise FileNotFoundError(f"Missing source file not found: {missing_path}")

    rows: list[dict[str, str]] = []
    with missing_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return rows
        for row in reader:
            if (row.get("originals_recipes") or "").strip():
                rows.append(row)
    return rows


def load_usda_ingredients(usda_path: Path) -> pd.DataFrame:
    """Load USDA ingredients as a searchable table."""

    if not usda_path.exists():
        raise FileNotFoundError(f"USDA ingredients file not found: {usda_path}")

    df = pd.read_csv(usda_path, low_memory=False)
    required = {"food_code", "food_name"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"USDA ingredients file is missing required columns: {sorted(missing)}")

    df = df.copy()
    df["food_code"] = df["food_code"].astype(str)
    df["food_name"] = df["food_name"].astype(str)
    df["food_name_normalized"] = df["food_name"].map(tokenize_for_matching)
    df = df[df["food_name_normalized"].astype(bool)]
    df = df.drop_duplicates(subset=["food_code"], keep="first")
    return df


def best_match_for_source(
    source_text: str,
    choices: Sequence[tuple[str, str]],
) -> tuple[str | None, float, str]:
    """Return the best USDA choice for a source ingredient.

    The returned score is the RapidFuzz score, and the scorer name is included
    for auditability.
    """

    query = tokenize_for_matching(source_text)
    if not query:
        return None, 0.0, "token_set_ratio"

    best_choice: str | None = None
    best_score = 0.0

    for choice_name, choice_key in choices:
        score = float(fuzz.token_set_ratio(query, choice_key))
        if score > best_score:
            best_choice = choice_name
            best_score = score

    if best_choice is None:
        return None, 0.0, "token_set_ratio"

    return best_choice, best_score, "token_set_ratio"


def propose_matches(
    missing_rows: Iterable[dict[str, str]],
    usda_df: pd.DataFrame,
    already_mapped: set[str],
    threshold: float,
) -> tuple[list[MatchResult], list[RejectionResult]]:
    """Create fuzzy mapping proposals for all recipe-origin missing ingredients."""

    choices: list[tuple[str, str]] = [
        (str(row.food_name), str(row.food_name_normalized))
        for row in usda_df.itertuples(index=False)
    ]
    choice_lookup = {
        row.food_name: (str(row.food_code), str(row.food_name))
        for row in usda_df.itertuples(index=False)
    }

    matches: list[MatchResult] = []
    rejections: list[RejectionResult] = []

    for row in missing_rows:
        source_normalized = (row.get("normalized") or "").strip()
        originals = split_originals(row.get("originals_recipes") or "")
        if not originals:
            continue

        for source_original in originals:
            source_key = normalize_text(source_original)
            if not source_key:
                continue
            if source_key in already_mapped:
                rejections.append(
                    RejectionResult(
                        source_normalized=source_normalized,
                        source_original=source_original,
                        best_food_code="",
                        best_food_name="",
                        best_score=0.0,
                        reason="already_mapped_in_ingredient_mapping_final",
                    )
                )
                continue

            best_choice, score, scorer_name = best_match_for_source(source_original, choices)
            if best_choice is None or score <= threshold:
                best_code, best_name = choice_lookup.get(best_choice, ("", "")) if best_choice else ("", "")
                rejections.append(
                    RejectionResult(
                        source_normalized=source_normalized,
                        source_original=source_original,
                        best_food_code=best_code,
                        best_food_name=best_name,
                        best_score=score,
                        reason=f"score_not_strictly_above_{int(threshold)}",
                    )
                )
                continue

            best_code, best_name = choice_lookup.get(best_choice, ("", ""))
            matches.append(
                MatchResult(
                    source_normalized=source_normalized,
                    source_original=source_original,
                    matched_food_code=best_code,
                    matched_food_name=best_name,
                    score=score,
                    scorer=scorer_name,
                )
            )

    return matches, rejections


def write_results(matches: Sequence[MatchResult], rejections: Sequence[RejectionResult]) -> None:
    """Write proposal and rejection CSVs for manual review."""

    MATCHES_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with MATCHES_OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source_normalized",
                "source_original",
                "matched_food_code",
                "matched_food_name",
                "score",
                "scorer",
            ],
        )
        writer.writeheader()
        for row in matches:
            writer.writerow(
                {
                    "source_normalized": row.source_normalized,
                    "source_original": row.source_original,
                    "matched_food_code": row.matched_food_code,
                    "matched_food_name": row.matched_food_name,
                    "score": f"{row.score:.2f}",
                    "scorer": row.scorer,
                }
            )

    with REJECTIONS_OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source_normalized",
                "source_original",
                "best_food_code",
                "best_food_name",
                "best_score",
                "reason",
            ],
        )
        writer.writeheader()
        for row in rejections:
            writer.writerow(
                {
                    "source_normalized": row.source_normalized,
                    "source_original": row.source_original,
                    "best_food_code": row.best_food_code,
                    "best_food_name": row.best_food_name,
                    "best_score": f"{row.best_score:.2f}",
                    "reason": row.reason,
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate fuzzy USDA match suggestions for unmapped recipe ingredients.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=85.0,
        help="Accept only matches with a RapidFuzz score strictly greater than this value (default: 85).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.threshold >= 100:
        raise ValueError("Threshold must be below 100 because the rule is strictly greater than the threshold.")

    already_mapped = load_existing_mapping_foods(MAPPING_FINAL_PATH)
    missing_rows = load_missing_sources(MISSING_PATH)
    usda_df = load_usda_ingredients(USDA_INGREDIENTS_PATH)

    matches, rejections = propose_matches(missing_rows, usda_df, already_mapped, args.threshold)
    write_results(matches, rejections)

    print(f"Loaded {len(missing_rows)} recipe-origin missing ingredient rows")
    print(f"Loaded {len(usda_df)} USDA ingredient candidates")
    print(f"Accepted matches: {len(matches)}")
    print(f"Rejected rows: {len(rejections)}")
    print(f"Wrote: {MATCHES_OUTPUT_PATH}")
    print(f"Wrote: {REJECTIONS_OUTPUT_PATH}")


if __name__ == "__main__":
    main()





