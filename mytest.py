"""
Ayurvedic Weekly Diet Planner — Fast MILP + Heuristic Mode
--------------------------------------------------------

This single Python file provides two planner modes:

1) **MILP-Fast** — a trimmed and optimized MILP that uses pre-filtering, reduced variables,
   solver time limit, and optional relaxations so it runs much faster than the full model.

2) **Heuristic (Greedy)** — a fast deterministic greedy allocator that builds each day's meals
   by selecting season/dosha-favored foods and filling macros incrementally. Runs instantly.

How to use
1) `pip install pulp pandas tabulate`  (and install GLPK if you want `GLPK_CMD`)
2) Run: `python ayurvedic_planner_fast.py` and set MODE at the top to either "milp_fast" or "heuristic".

Notes
- Starter food catalog is the same as before but will be prefiltered by season + top-K per meal.
- MILP-Fast gives better adherence to nutrition targets but may still be slower than heuristic depending on settings.
- Heuristic is recommended for interactive use and quick iteration.

"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

import pandas as pd
from tabulate import tabulate

from DemoDB import getData

try:
    import pulp
except ImportError:
    raise SystemExit("Please install PuLP first: pip install pulp")

# -------------------------------
# Mode selection
# -------------------------------
# Choose mode: "milp_fast" or "heuristic"
MODE = "milp_fast"

# -------------------------------
# User profile & tuning knobs
# -------------------------------
USER_PROFILE = {
    "dominant_dosha": "Vata",
    "season": "LateWinter",
    "targets": {
        "calories": 2200,
        "protein_g": 80,
        "fat_g": 70,
        "carb_g": 280,
        "sugar_g": 45,
        "sodium_mg": 2000,
        "satfat_g": 20,
        "calorie_tolerance": 0.10,  # relaxed compared to previous
        "macro_tolerance": 0.25,
    },
    "max_items_per_meal": 1,  # reduce to 1 for much faster MILP
    "min_repeat_gap_days": 2,
}

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MEALS = ["breakfast", "lunch", "snack", "dinner"]

# -------------------------------
# Food dataclass and catalog (same items as earlier)
# -------------------------------
@dataclass
class Food:
    name: str
    food_type: str
    season_tags: Set[str]
    dosha_score: Dict[str, int]
    per_serving: Dict[str, float]
    incompatible_with: Set[str] = field(default_factory=set)

NUTRIENTS = ["calories", "protein_g", "fat_g", "carb_g", "sugar_g", "sodium_mg", "satfat_g"]

# NOTE: use the same FOODS list as the original script. For brevity here we include a reduced subset.
FOODS = getData()

# Normalize seasons
ALL_SEASONS = {"Summer", "Monsoon", "Autumn", "EarlyWinter", "LateWinter", "Winter", "Spring"}
for f in FOODS:
    if "All" in f.season_tags:
        f.season_tags = set(ALL_SEASONS)

# Quick lookups
FOOD_INDEX = {f.name: i for i,f in enumerate(FOODS)}

# -------------------------------
# Utility: prefilter foods by season and dosha rank
# -------------------------------

def prefilter_foods(profile: Dict, foods: List[Food], top_k_per_meal: int = 8) -> List[Food]:
    season = profile["season"]
    dom = profile["dominant_dosha"]
    if isinstance(dom, str):
        dom = [dom]

    # Score: season match + dosha score
    scored = []
    for f in foods:
        season_match = 1 if season in f.season_tags else 0
        ds = sum(f.dosha_score.get(d, 0) for d in dom)
        score = 2*season_match + ds
        scored.append((score, f))

    scored.sort(key=lambda x: x[0], reverse=True)
    # keep top K
    kept = [f for _, f in scored[:top_k_per_meal]]
    return kept

# -------------------------------
# MILP-Fast: reduced variables & solver tuning
# -------------------------------

def plan_week_milp_fast(profile: Dict, foods: List[Food]) -> Tuple[pd.DataFrame, Dict]:
    # Prefilter foods
    foods = prefilter_foods(profile, foods, top_k_per_meal=6)  # aggressive trim

    tgt = profile["targets"]
    max_items = profile.get("max_items_per_meal", 1)
    gap = profile.get("min_repeat_gap_days", 2)

    prob = pulp.LpProblem("MilpFast", pulp.LpMinimize)

    # Variables per day/meal: choose at most max_items distinct foods (binary y)
    y = {}
    for d in range(7):
        for m in range(len(MEALS)):
            for i in range(len(foods)):
                y[(d,m,i)] = pulp.LpVariable(f"y_{d}_{m}_{i}", lowBound=0, upBound=1, cat=pulp.LpBinary)

    # Limit items per meal
    for d in range(7):
        for m in range(len(MEALS)):
            prob += pulp.lpSum(y[(d,m,i)] for i in range(len(foods))) <= max_items

    # No-repeat (optional: we relax fully in fast mode)
    # Commented out or keep depending on speed requirements
    for i in range(len(foods)):
        for d in range(7):
            for h in range(1, gap+1):
                if d + h < 7:
                    prob += pulp.lpSum(y[(d,m,i)] for m in range(len(MEALS))) + pulp.lpSum(y[(d+h,m,i)] for m in range(len(MEALS))) <= 1

    # Nutrient sums computed from y assuming 1 serving per chosen item (simplification)
    # This reduces integer variable count (no x variables)
    def day_nutrient(d, nutrient):
        return pulp.lpSum(y[(d,m,i)] * foods[i].per_serving[nutrient] for m in range(len(MEALS)) for i in range(len(foods)))

    cal_lo = (1 - tgt["calorie_tolerance"]) * tgt["calories"]
    cal_hi = (1 + tgt["calorie_tolerance"]) * tgt["calories"]

    # Deviation variables
    dev_plus = [pulp.LpVariable(f"dev_plus_{d}", lowBound=0) for d in range(7)]
    dev_minus = [pulp.LpVariable(f"dev_minus_{d}", lowBound=0) for d in range(7)]

    for d in range(7):
        prob += day_nutrient(d, "calories") - tgt["calories"] == dev_plus[d] - dev_minus[d]
        prob += day_nutrient(d, "calories") >= cal_lo
        prob += day_nutrient(d, "calories") <= cal_hi
        for macro in ["protein_g","fat_g","carb_g"]:
            prob += day_nutrient(d, macro) >= (1 - tgt["macro_tolerance"]) * tgt[macro]
            prob += day_nutrient(d, macro) <= (1 + tgt["macro_tolerance"]) * tgt[macro]
        prob += day_nutrient(d, "sugar_g") <= tgt["sugar_g"]
        prob += day_nutrient(d, "sodium_mg") <= tgt["sodium_mg"]
        prob += day_nutrient(d, "satfat_g") <= tgt["satfat_g"]

    # Objective: minimize calorie deviation - dosha/season bonuses
    bonuses = []
    penalties = []
    for d in range(7):
        bonuses += [-0.6 * y[(d,m,i)] * (1 if profile["season"] in foods[i].season_tags else 0) for m in range(len(MEALS)) for i in range(len(foods))]
        bonuses += [-0.4 * y[(d,m,i)] * sum(foods[i].dosha_score.get(profile["dominant_dosha"],0) for _ in [0]) for m in range(len(MEALS)) for i in range(len(foods))]
        penalties += [0.02 * y[(d,m,i)] * foods[i].per_serving["sugar_g"] for m in range(len(MEALS)) for i in range(len(foods))]
    obj = pulp.lpSum(dev_plus) + pulp.lpSum(dev_minus) + pulp.lpSum(penalties) + pulp.lpSum(bonuses)
    prob += obj

    # Solve with time limit
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=12)
    prob.solve(solver)

    # Build plan output from y variables (each chosen item counts as 1 serving)
    rows = []
    for d, day in enumerate(DAYS):
        for m, meal in enumerate(MEALS):
            picks = []
            for i,f in enumerate(foods):
                val = int(round(pulp.value(y[(d,m,i)]) or 0))
                if val > 0:
                    picks.append((f.name, val))
            rows.append({"day":day, "meal":meal, "items":picks})
    plan_df = pd.DataFrame(rows)

    # daily nutrient summary (compute actual sums)
    nut_rows = []
    for d, day in enumerate(DAYS):
        s = {k:0.0 for k in NUTRIENTS}
        for m in range(len(MEALS)):
            for i,f in enumerate(foods):
                if int(round(pulp.value(y[(d,m,i)]) or 0)) > 0:
                    for k in NUTRIENTS:
                        s[k] += f.per_serving[k]
        s.update({"day":day, "cal_dev": float((pulp.value(dev_plus[d]) or 0) + (pulp.value(dev_minus[d]) or 0))})
        nut_rows.append(s)
    nut_df = pd.DataFrame(nut_rows)[["day"] + NUTRIENTS + ["cal_dev"]]

    return plan_df, {"nutrition": nut_df, "status": pulp.LpStatus[prob.status], "objective": pulp.value(prob.objective)}

# -------------------------------
# Heuristic: greedy per meal fill
# -------------------------------

def plan_week_heuristic(profile: Dict, foods: List[Food]) -> Tuple[pd.DataFrame, Dict]:
    foods = prefilter_foods(profile, foods, top_k_per_meal=10)
    tgt = profile["targets"]

    # Convert foods to DataFrame for convenience
    df = pd.DataFrame([{
        "name": f.name,
        **{k: f.per_serving[k] for k in NUTRIENTS},
        "score": sum(f.dosha_score.get(profile["dominant_dosha"],0) for _ in [0]) + (1 if profile["season"] in f.season_tags else 0)
    } for f in foods])

    plan_rows = []
    nut_rows = []

    # For each day, try to greedily pick items per meal
    for d, day in enumerate(DAYS):
        day_nut = {k:0.0 for k in NUTRIENTS}
        for m, meal in enumerate(MEALS):
            picks = []
            # sort candidates by (score / calories) to favor nutrient-dense dosha/season items
            candidates = df.sort_values(by=["score", "protein_g"], ascending=[False, False]).to_dict('records')
            # try pick up to max_items_per_meal distinct items
            remaining_slots = profile.get("max_items_per_meal",1)
            for cand in candidates:
                if remaining_slots <= 0:
                    break
                # simple check: won't exceed sugar/satfat/sodium
                if day_nut["sugar_g"] + cand["sugar_g"] > tgt["sugar_g"]:
                    continue
                if day_nut["satfat_g"] + cand["satfat_g"] > tgt["satfat_g"]:
                    continue
                if day_nut["sodium_mg"] + cand["sodium_mg"] > tgt["sodium_mg"]:
                    continue
                # add item
                picks.append((cand["name"], 1))
                for k in NUTRIENTS:
                    day_nut[k] += cand[k]
                remaining_slots -= 1
            plan_rows.append({"day":day, "meal":meal, "items":picks})
        day_nut.update({"day":day, "cal_dev": abs(day_nut["calories"] - tgt["calories"])})
        nut_rows.append(day_nut)

    plan_df = pd.DataFrame(plan_rows)
    nut_df = pd.DataFrame(nut_rows)[["day"] + NUTRIENTS + ["cal_dev"]]
    return plan_df, {"nutrition": nut_df, "status": "heuristic", "objective": None}

# -------------------------------
# Pretty print (small)
# -------------------------------

def pretty_print(plan_df: pd.DataFrame, extras: Dict):
    display_rows = []
    for day in DAYS:
        for meal in MEALS:
            items = plan_df[(plan_df["day"]==day)&(plan_df["meal"]==meal)]["items"].values[0]
            if items:
                txt = "; ".join([f"{name} (x{qty})" for name,qty in items])
            else:
                txt = "—"
            display_rows.append([day, meal.title(), txt])
    print("=== Weekly Plan ===")
    print(tabulate(display_rows, headers=["Day","Meal","Items"], tablefmt="github"))
    print("=== Daily Nutrition ===")
    print(tabulate(extras["nutrition"], headers="keys", tablefmt="github", floatfmt=".1f"))
    print("Status:", extras.get("status"), "Objective:", extras.get("objective"))

# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":
    if MODE == "heuristic":
        plan, extras = plan_week_milp_fast(USER_PROFILE, FOODS)
    else:
        plan, extras = plan_week_heuristic(USER_PROFILE, FOODS)
    pretty_print(plan, extras)

    # Export if needed
    # plan.to_csv("weekly_plan.csv", index=False)
    # extras["nutrition"].to_csv("daily_nutrition.csv", index=False)
