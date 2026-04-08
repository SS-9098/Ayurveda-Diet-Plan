#!/usr/bin/env python3
"""Find ingredients present in unique ingredient lists but missing from mapping.

Produces usable/missing_mappings_from_unique_sources.csv with columns:
  ingredient_original, normalized, in_unique_recipes, in_unique_ingredients1, recipes_count

Also prints a summary and top missing ingredients by recipes_count.
"""
import csv
import re
from collections import Counter
from pathlib import Path


def normalize(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip().lower()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1].strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(".,;:/\n\t\r")
    return s


def load_mapping(mapping_path: Path):
    mapped = set()
    with mapping_path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return mapped
        if 'food_ingredient' not in reader.fieldnames:
            f.seek(0)
            r2 = csv.reader(f)
            next(r2, None)
            for row in r2:
                if not row:
                    continue
                mapped.add(normalize(row[0]))
            return mapped
        for row in reader:
            val = row.get('food_ingredient')
            if val is None:
                continue
            mapped.add(normalize(val))
    return mapped


def load_unique_list(path: Path, has_header=False):
    s = []
    with path.open(encoding='utf-8') as f:
        if has_header:
            next(f, None)
        for line in f:
            line = line.strip()
            if not line:
                continue
            s.append(line)
    return s


def count_in_recipes(recipes_path: Path):
    cnt = Counter()
    with recipes_path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row.get('ingredient_name_org') or ''
            n = normalize(raw)
            if n:
                cnt[n] += 1
    return cnt


def main():
    base = Path(__file__).resolve().parents[1]
    mapping_path = base / 'usable' / 'ingredient_mapping_final.csv'
    recipes_path = base / 'usable' / 'recipes.csv'
    u_recipes = Path(__file__).resolve().parents[0] / 'unique_ingredients.txt'
    u_ing1 = Path(__file__).resolve().parents[0] / 'unique_ingredients_1.txt'
    out_path = base / 'usable' / 'missing_mappings_from_unique_sources.csv'

    if not mapping_path.exists():
        print('mapping file not found:', mapping_path)
        return
    if not u_recipes.exists() and not u_ing1.exists():
        print('unique files not found in scripts/ folder')
        return

    mapped = load_mapping(mapping_path)
    print(f'Loaded {len(mapped)} mapping entries')

    # load unique lists
    recipes_list = []
    if u_recipes.exists():
        recipes_list = load_unique_list(u_recipes, has_header=False)
    ing1_list = []
    if u_ing1.exists():
        # this file has header 'full_name'
        ing1_list = load_unique_list(u_ing1, has_header=True)

    # build normalized sets and original->norm maps
    rec_norm_map = {}
    for raw in recipes_list:
        n = normalize(raw)
        if n:
            rec_norm_map.setdefault(n, set()).add(raw)

    ing1_norm_map = {}
    for raw in ing1_list:
        n = normalize(raw)
        if n:
            ing1_norm_map.setdefault(n, set()).add(raw)

    # count occurrences in recipes.csv
    recipes_counts = Counter()
    if recipes_path.exists():
        recipes_counts = count_in_recipes(recipes_path)

    # union of normalized items from both lists
    all_norms = set(rec_norm_map.keys()) | set(ing1_norm_map.keys())

    # select those not in mapping
    missing = []
    for n in sorted(all_norms):
        if n not in mapped:
            row = {
                'normalized': n,
                'in_unique_recipes': '1' if n in rec_norm_map else '0',
                'in_unique_ingredients1': '1' if n in ing1_norm_map else '0',
                'recipes_count': str(recipes_counts.get(n, 0)),
                'originals_recipes': '|'.join(sorted(rec_norm_map.get(n, []))) if n in rec_norm_map else '',
                'originals_ingredients1': '|'.join(sorted(ing1_norm_map.get(n, []))) if n in ing1_norm_map else '',
            }
            missing.append(row)

    # write CSV
    fieldnames = ['normalized', 'originals_recipes', 'originals_ingredients1', 'in_unique_recipes', 'in_unique_ingredients1', 'recipes_count']
    with out_path.open('w', newline='', encoding='utf-8') as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames)
        writer.writeheader()
        for r in missing:
            writer.writerow(r)

    print(f'Wrote {len(missing)} missing mappings to {out_path}')

    # print top 20 by recipes_count
    with_counts = [r for r in missing if int(r['recipes_count']) > 0]
    sorted_by_count = sorted(with_counts, key=lambda x: int(x['recipes_count']), reverse=True)
    topn = sorted_by_count[:20]
    if topn:
        print('\nTop missing ingredients by recipes occurrences:')
        for r in topn:
            print(f"{r['normalized']} — count={r['recipes_count']} — from_recipes={r['originals_recipes']}")


if __name__ == '__main__':
    main()

