#!/usr/bin/env python3
"""Generate a CSV listing dropped recipes and their unavailable ingredients.

Output: usable/dropped_recipes_unavailable_ingredients.csv
Columns: recipe_code_org, recipe_code, recipe_name_org, recipe_name,
         missing_count, ingredients_unavailable
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
    s = re.sub(r"\s+", " ", s)
    s = s.strip(".,;:/\n\t\r")
    return s


def load_mapping_food_ingredients(mapping_path: Path):
    foods = set()
    with mapping_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return foods
        if 'food_ingredient' not in reader.fieldnames:
            # fallback: first column
            f.seek(0)
            r2 = csv.reader(f)
            next(r2, None)
            for row in r2:
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


def build_recipe_groups(recipes_path: Path):
    groups = defaultdict(list)
    with recipes_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit("recipes file seems empty or malformed")
        for row in reader:
            key = row.get('recipe_code_org') or row.get('recipe_code') or row.get('recipe_name_org')
            groups[key].append(row)
    return groups


def report_dropped(recipes_path: Path, mapping_path: Path, output_path: Path):
    mapping_foods = load_mapping_food_ingredients(mapping_path)
    groups = build_recipe_groups(recipes_path)

    rows_out = []
    for key, rows in groups.items():
        # map normalized -> set(original strings)
        norm_to_originals = defaultdict(set)
        for r in rows:
            orig = r.get('ingredient_name_org', '')
            norm = normalize(orig)
            norm_to_originals[norm].add(orig.strip())

        # identify missing normalized ingredient names
        missing_norms = [n for n in norm_to_originals.keys() if (n == '' or n not in mapping_foods)]
        if not missing_norms:
            continue

        # prepare list of originals for missing ones (join multiple originals with '|')
        missing_originals = []
        for n in missing_norms:
            originals = sorted(x for x in norm_to_originals[n] if x)
            if originals:
                missing_originals.append("|".join(originals))
            else:
                missing_originals.append('')

        # pick representative recipe metadata from first row
        first = rows[0]
        out_row = {
            'recipe_code_org': first.get('recipe_code_org', ''),
            'recipe_code': first.get('recipe_code', ''),
            'recipe_name_org': first.get('recipe_name_org', ''),
            'recipe_name': first.get('recipe_name', ''),
            'missing_count': str(len(missing_norms)),
            'ingredients_unavailable': ';'.join(missing_originals),
        }
        rows_out.append(out_row)

    # write output
    fieldnames = ['recipe_code_org', 'recipe_code', 'recipe_name_org', 'recipe_name', 'missing_count', 'ingredients_unavailable']
    with output_path.open('w', newline='', encoding='utf-8') as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows_out:
            writer.writerow(r)

    return len(rows_out)


def main():
    base = Path(__file__).resolve().parents[1] / 'usable'
    recipes_path = base / 'recipes.csv'
    mapping_path = base / 'ingredient_mapping_final.csv'
    output_path = base / 'dropped_recipes_unavailable_ingredients.csv'

    if not recipes_path.exists():
        print(f"recipes file not found: {recipes_path}")
        return
    if not mapping_path.exists():
        print(f"mapping file not found: {mapping_path}")
        return

    count = report_dropped(recipes_path, mapping_path, output_path)
    print(f"Wrote {count} dropped recipes to {output_path}")


if __name__ == '__main__':
    main()

