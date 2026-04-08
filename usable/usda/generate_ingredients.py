#!/usr/bin/env python3
"""Generate `ingredients.csv` from USDA source tables.

This script builds a wide, one-row-per-food table using:
- `food.csv` for `fdc_id`, `description`, and metadata
- `nutrient(contains_all_units_of_unique_nutr).csv` for nutrient labels and units
- `food_nutrient.csv` for the bridge values

Only `foundation_food` rows from `food.csv` are included.
The output is written to `ingredients.csv` in the same directory.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
FOOD_PATH = BASE_DIR / "food.csv"
NUTRIENT_PATH = BASE_DIR / "nutrient(contains_all_units_of_unique_nutr).csv"
FOOD_NUTRIENT_PATH = BASE_DIR / "food_nutrient.csv"
OUTPUT_PATH = BASE_DIR / "ingredients.csv"


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


def slugify(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = text.replace("%", " percent ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def build_ingredients() -> pd.DataFrame:
    food = pd.read_csv(
        FOOD_PATH,
        usecols=["fdc_id", "data_type", "description", "food_category_id", "publication_date"],
        low_memory=False,
    )
    food = food.loc[food["data_type"].eq("foundation_food")].copy()
    food = food.drop_duplicates(subset=["fdc_id"], keep="first")
    food["food_code"] = food["fdc_id"]
    food["food_name"] = food["description"].map(normalize_food_name)
    food = food[["food_code", "food_name", "food_category_id", "publication_date"]]

    nutrients = pd.read_csv(
        NUTRIENT_PATH,
        usecols=["id", "name", "unit_name", "nutrient_nbr", "rank"],
        low_memory=False,
    )
    food_nutrient = pd.read_csv(
        FOOD_NUTRIENT_PATH,
        usecols=["fdc_id", "nutrient_id", "amount"],
        low_memory=False,
    )

    used_ids = set(food_nutrient["nutrient_id"].dropna().astype(int).tolist())
    nutrients = nutrients.loc[nutrients["id"].isin(used_ids)].copy()
    nutrients["base_name"] = nutrients["name"].map(slugify)
    nutrients["unit_slug"] = nutrients["unit_name"].map(slugify)

    base_counts = nutrients["base_name"].value_counts()
    used_column_names: set[str] = set()
    column_names = []

    for row in nutrients.itertuples(index=False):
        base_name = str(row.base_name)
        unit_slug = str(row.unit_slug)
        candidate = base_name
        if base_counts[base_name] > 1:
            candidate = f"{base_name}_{unit_slug}" if unit_slug else base_name
        if not candidate or candidate in used_column_names:
            candidate = f"{base_name}_{row.id}" if base_name else f"nutrient_{row.id}"
        if candidate in used_column_names:
            candidate = f"{candidate}_{row.id}"
        used_column_names.add(candidate)
        column_names.append(candidate)

    nutrients["column_name"] = column_names

    merged = food_nutrient.merge(
        nutrients[["id", "column_name", "rank"]],
        left_on="nutrient_id",
        right_on="id",
        how="inner",
    )
    merged = merged.merge(food, left_on="fdc_id", right_on="food_code", how="inner")
    merged = merged[["food_code", "food_name", "food_category_id", "publication_date", "column_name", "amount", "rank"]]

    wide = merged.pivot(
        index=["food_code", "food_name", "food_category_id", "publication_date"],
        columns="column_name",
        values="amount",
    ).reset_index()

    ordered_nutrients = [str(column) for column in nutrients.sort_values(["rank", "id"])["column_name"].tolist()]
    ordered_nutrients = [column for column in ordered_nutrients if column in wide.columns]
    ordered_columns: list[str] = ["food_code", "food_name", "food_category_id", "publication_date"] + ordered_nutrients
    return wide.loc[:, ordered_columns]


def main() -> None:
    ingredients = build_ingredients()
    ingredients.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {OUTPUT_PATH}")
    print(f"rows={len(ingredients)} cols={len(ingredients.columns)}")


if __name__ == "__main__":
    main()


