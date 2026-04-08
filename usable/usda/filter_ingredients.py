#!/usr/bin/env python3
"""Filter `ingredients.csv` down to the USDA-mapped ingredient list.

This script keeps the full column set from `ingredients.csv` and writes a new
`ingredients_filtered.csv` containing only rows whose normalized `food_name`
appears in `ingredients_usda_mapped`.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
INPUT_PATH = BASE_DIR / "ingredients.csv"
MAPPING_PATH = BASE_DIR / "ingredients_usda_mapped"
OUTPUT_PATH = BASE_DIR / "ingredients_filtered.csv"


def normalize_food_name(value: object) -> str:
    if pd.isna(value):  # type: ignore[arg-type]
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\xa0", " ")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s*\(\s*", " (", text)
    text = re.sub(r"\s*\)\s*", ")", text)
    return text.strip(" ,;")


def load_whitelist(path: Path) -> set[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    whitelist = {
        normalize_food_name(line)
        for line in lines
        if normalize_food_name(line) and normalize_food_name(line) != "usda_mapping"
    }
    return whitelist


def build_filtered_ingredients() -> pd.DataFrame:
    ingredients = pd.read_csv(INPUT_PATH, low_memory=False)
    if "food_name" not in ingredients.columns:
        raise ValueError(f"Expected a 'food_name' column in {INPUT_PATH}")

    whitelist = load_whitelist(MAPPING_PATH)
    normalized_names = ingredients["food_name"].map(normalize_food_name)
    filtered = ingredients.loc[normalized_names.isin(whitelist)].copy()
    return filtered


def main() -> None:
    filtered = build_filtered_ingredients()
    filtered.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {OUTPUT_PATH}")
    print(f"rows={len(filtered)} cols={len(filtered.columns)}")


if __name__ == "__main__":
    main()
