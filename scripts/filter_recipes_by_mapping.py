#!/usr/bin/env python3
"""Filter recipes: keep only recipes where every ingredient_name_org is present
in usable/ingredient_mapping_final.csv's food_ingredient column.

Output is written to usable/recipes_filtered.csv with the same columns and
row structure as usable/recipes.csv.
"""
import csv
import re
from collections import defaultdict
from pathlib import Path


def normalize(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = s.strip().lower()
    # remove surrounding quotes
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1].strip()
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    # remove trailing/leading punctuation
    s = s.strip(".,;:/\n\t\r")
    return s


def load_mapping_food_ingredients(mapping_path: Path):
    foods = set()
    with mapping_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # support files that may not have headers by trying first two columns
        if 'food_ingredient' not in reader.fieldnames:
            # fallback: assume first column
            f.seek(0)
            reader = csv.reader(f)
            # skip header row then read
            header = next(reader, None)
            # first col index 0
            for row in reader:
                if not row:
                    continue
                foods.add(normalize(row[0]))
            return foods

        for row in reader:
            raw = row.get('food_ingredient')
            if raw is None:
                continue
            foods.add(normalize(raw))
    return foods


def filter_recipes(recipes_path: Path, mapping_foods: set, output_path: Path):
    groups = defaultdict(list)
    # read recipes and group by recipe_code_org
    with recipes_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise SystemExit("recipes file seems empty or malformed")
        for row in reader:
            key = row.get('recipe_code_org') or row.get('recipe_code') or row.get('recipe_name_org')
            groups[key].append(row)

    kept = 0
    total_recipes = len(groups)
    total_rows_written = 0

    with output_path.open('w', newline='', encoding='utf-8') as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames)
        writer.writeheader()
        for key, rows in groups.items():
            # collect unique ingredient_name_org values for this recipe
            ingr_names = set()
            for r in rows:
                ingr_names.add(normalize(r.get('ingredient_name_org', '')))

            # empty ingredient names -> treat as missing mapping (skip)
            if not ingr_names:
                continue

            # check all are in mapping
            all_mapped = True
            for ing in ingr_names:
                if ing == '':
                    all_mapped = False
                    break
                if ing not in mapping_foods:
                    all_mapped = False
                    break

            if all_mapped:
                kept += 1
                for r in rows:
                    writer.writerow(r)
                    total_rows_written += 1

    return {
        'total_recipes': total_recipes,
        'kept_recipes': kept,
        'rows_written': total_rows_written,
    }


def main():
    base = Path(__file__).resolve().parents[1] / 'usable'
    recipes_path = base / 'recipes.csv'
    mapping_path = base / 'ingredient_mapping_final.csv'
    output_path = base / 'recipes_filtered.csv'

    if not recipes_path.exists():
        print(f"recipes file not found: {recipes_path}")
        return
    if not mapping_path.exists():
        print(f"mapping file not found: {mapping_path}")
        return

    mapping_foods = load_mapping_food_ingredients(mapping_path)
    print(f"Loaded {len(mapping_foods)} mapped food_ingredient entries")

    stats = filter_recipes(recipes_path, mapping_foods, output_path)

    print("Filter complete")
    print(f"Total recipes found: {stats['total_recipes']}")
    print(f"Recipes kept (all ingredients mapped): {stats['kept_recipes']}")
    print(f"Rows written to {output_path}: {stats['rows_written']}")


if __name__ == '__main__':
    main()

