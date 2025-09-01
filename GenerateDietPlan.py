"""
Ayurvedic Weekly Diet Planner
---------------------------------

This script builds a *weekly* meal plan (7 days × {breakfast, lunch, snack, dinner})
that follows high-level Ayurvedic principles **and** hits daily nutrition targets
(calories, protein, fat, carbs, sugar, sodium, saturated fat).

How it works
- You define a *user profile*: dosha focus (Vata/Pitta/Kapha), season, and daily nutrient targets.
- A small starter food catalog is included with: per-serving nutrition, dosha suitability, season tags, and food-combination rules.
- We solve a mixed-integer linear program (MILP) using PuLP to pick portions (in 0.5-serving steps) for each meal slot.
- Hard rules: avoid incompatible pairings, limit items per meal, avoid repeating the same dish too often.
- Soft rules (objective): favor season-appropriate + dosha-pacifying foods, penalize excess sugar/sat fat/sodium, and minimize deviation from calorie target.

Quick start
1) `pip install pulp pandas tabulate`
2) Run: `python ayurvedic_meal_planner.py`
3) Tweak `USER_PROFILE` and expand `FOODS` with your items.

Notes
- Values in the starter catalog are approximate placeholders for demo purposes.
- Always consult a qualified practitioner for personalized medical/diet advice.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

import pandas as pd
from tabulate import tabulate

try:
    import pulp
except ImportError:
    raise SystemExit("Please install PuLP first: pip install pulp")

# -------------------------------
# User profile & knobs
# -------------------------------
USER_PROFILE = {
    "dominant_dosha": "Vata",   # one of: "Vata", "Pitta", "Kapha" (string or list for multiple)
    "season": "LateWinter",      # examples: "Summer", "Monsoon", "Autumn", "EarlyWinter", "LateWinter", "Spring"
    # Daily Nutrition Targets (approx). Adjust to your needs.
    "targets": {
        "calories": 2200,
        "protein_g": 80,
        "fat_g": 70,
        "carb_g": 280,
        "sugar_g": 45,
        "sodium_mg": 2000,
        "satfat_g": 20,
        # Tolerances used in constraints (± for hard bounds)
        "calorie_tolerance": 0.07,  # ±7%
        "macro_tolerance": 0.20,    # ±20% for protein/fat/carb
    },
    # Planning preferences
    "max_items_per_meal": 2,
    "min_repeat_gap_days": 2,  # don't repeat the exact same dish within N days
}

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MEALS = ["breakfast", "lunch", "snack", "dinner"]

# -------------------------------
# Food catalog schema
# -------------------------------
@dataclass
class Food:
    name: str
    food_type: str                  # e.g. "grain", "legume", "veg", "fruit", "dairy", "meat", "spice", "beverage"
    season_tags: Set[str]           # seasons where it's particularly favored
    dosha_score: Dict[str, int]     # higher is more pacifying for that dosha: {"Vata": +2, "Pitta": +1, "Kapha": 0, ...}
    per_serving: Dict[str, float]   # nutrition per serving (g or mg as indicated)
    incompatible_with: Set[str] = field(default_factory=set)  # names of foods it must not pair with in the SAME meal

# Nutrition keys expected in per_serving
NUTRIENTS = ["calories", "protein_g", "fat_g", "carb_g", "sugar_g", "sodium_mg", "satfat_g"]

# -------------------------------
# Starter catalog (simplified)
# -------------------------------
# NB: These are rough demo values (not authoritative). Replace with your lab/label data.
FOODS: List[Food] = [
    Food(
        name="Kitchari (mung dal + rice)", food_type="combo", season_tags={"Monsoon", "Autumn", "LateWinter"},
        dosha_score={"Vata": 3, "Pitta": 2, "Kapha": 1},
        per_serving={"calories": 350, "protein_g": 14, "fat_g": 8, "carb_g": 58, "sugar_g": 3, "sodium_mg": 400, "satfat_g": 1.5},
        incompatible_with=set(),
    ),
    Food(
        name="Plain Rice (steamed)", food_type="grain", season_tags={"All"},
        dosha_score={"Vata": 2, "Pitta": 2, "Kapha": 0},
        per_serving={"calories": 200, "protein_g": 4, "fat_g": 0.5, "carb_g": 45, "sugar_g": 0.2, "sodium_mg": 0, "satfat_g": 0.1},
    ),
    Food(
        name="Whole Wheat Chapati", food_type="grain", season_tags={"All"},
        dosha_score={"Vata": 1, "Pitta": 1, "Kapha": 0},
        per_serving={"calories": 120, "protein_g": 4, "fat_g": 2, "carb_g": 22, "sugar_g": 0.5, "sodium_mg": 120, "satfat_g": 0.3},
    ),
    Food(
        name="Moong Dal (cooked)", food_type="legume", season_tags={"All"},
        dosha_score={"Vata": 2, "Pitta": 2, "Kapha": 1},
        per_serving={"calories": 230, "protein_g": 16, "fat_g": 1, "carb_g": 40, "sugar_g": 2, "sodium_mg": 10, "satfat_g": 0.2},
    ),
    Food(
        name="Paneer (fresh)", food_type="dairy", season_tags={"LateWinter", "EarlyWinter"},
        dosha_score={"Vata": 2, "Pitta": -1, "Kapha": -1},
        per_serving={"calories": 265, "protein_g": 18, "fat_g": 20, "carb_g": 3, "sugar_g": 2, "sodium_mg": 20, "satfat_g": 12},
        incompatible_with={"Citrus Fruits", "Mango", "Raw Banana", "Fish"},
    ),
    Food(
        name="Curd (plain, room temp)", food_type="dairy", season_tags={"LateWinter", "EarlyWinter", "Monsoon"},
        dosha_score={"Vata": 1, "Pitta": -1, "Kapha": -2},
        per_serving={"calories": 150, "protein_g": 8, "fat_g": 6, "carb_g": 16, "sugar_g": 12, "sodium_mg": 120, "satfat_g": 3.5},
        incompatible_with={"Mango", "Citrus Fruits", "Fish"},
    ),
    Food(
        name="Buttermilk (spiced)", food_type="beverage", season_tags={"Summer", "Monsoon"},
        dosha_score={"Vata": 1, "Pitta": 2, "Kapha": -1},
        per_serving={"calories": 90, "protein_g": 4, "fat_g": 2, "carb_g": 14, "sugar_g": 8, "sodium_mg": 180, "satfat_g": 1.2},
        incompatible_with={"Mango", "Citrus Fruits"},
    ),
    Food(
        name="Ghee (1 tbsp)", food_type="fat", season_tags={"All"},
        dosha_score={"Vata": 2, "Pitta": 1, "Kapha": -1},
        per_serving={"calories": 120, "protein_g": 0, "fat_g": 14, "carb_g": 0, "sugar_g": 0, "sodium_mg": 0, "satfat_g": 9},
    ),
    Food(
        name="Vegetable Sabzi (seasonal)", food_type="veg", season_tags={"All"},
        dosha_score={"Vata": 2, "Pitta": 1, "Kapha": 1},
        per_serving={"calories": 180, "protein_g": 5, "fat_g": 6, "carb_g": 26, "sugar_g": 6, "sodium_mg": 250, "satfat_g": 1},
        incompatible_with=set(),
    ),
    Food(
        name="Leafy Greens (stir-fry)", food_type="veg", season_tags={"Winter", "Spring", "LateWinter"},
        dosha_score={"Vata": 1, "Pitta": 2, "Kapha": 2},
        per_serving={"calories": 80, "protein_g": 4, "fat_g": 3, "carb_g": 10, "sugar_g": 2, "sodium_mg": 180, "satfat_g": 0.5},
    ),
    Food(
        name="Khichdi (veg-heavy)", food_type="combo", season_tags={"Monsoon", "LateWinter", "Autumn"},
        dosha_score={"Vata": 3, "Pitta": 2, "Kapha": 1},
        per_serving={"calories": 320, "protein_g": 12, "fat_g": 7, "carb_g": 54, "sugar_g": 3, "sodium_mg": 380, "satfat_g": 1.2},
    ),
    Food(
        name="Upma (semolina veg)", food_type="grain", season_tags={"All"},
        dosha_score={"Vata": 1, "Pitta": 1, "Kapha": 0},
        per_serving={"calories": 300, "protein_g": 8, "fat_g": 9, "carb_g": 46, "sugar_g": 3, "sodium_mg": 350, "satfat_g": 2},
    ),
    Food(
        name="Idli (2 pcs)", food_type="grain", season_tags={"All"},
        dosha_score={"Vata": 2, "Pitta": 2, "Kapha": 0},
        per_serving={"calories": 150, "protein_g": 6, "fat_g": 1.5, "carb_g": 30, "sugar_g": 1, "sodium_mg": 180, "satfat_g": 0.4},
    ),
    Food(
        name="Sambar (1 cup)", food_type="legume", season_tags={"All"},
        dosha_score={"Vata": 1, "Pitta": 1, "Kapha": 1},
        per_serving={"calories": 120, "protein_g": 5, "fat_g": 3, "carb_g": 18, "sugar_g": 5, "sodium_mg": 350, "satfat_g": 0.4},
    ),
    Food(
        name="Coconut Chutney (2 tbsp)", food_type="fat", season_tags={"Summer", "Monsoon"},
        dosha_score={"Vata": 1, "Pitta": 1, "Kapha": -1},
        per_serving={"calories": 100, "protein_g": 1, "fat_g": 10, "carb_g": 3, "sugar_g": 1, "sodium_mg": 80, "satfat_g": 8},
    ),
    Food(
        name="Oats Porridge (milk)", food_type="grain", season_tags={"LateWinter", "EarlyWinter"},
        dosha_score={"Vata": 2, "Pitta": 0, "Kapha": -1},
        per_serving={"calories": 280, "protein_g": 10, "fat_g": 7, "carb_g": 42, "sugar_g": 10, "sodium_mg": 150, "satfat_g": 2.5},
        incompatible_with={"Citrus Fruits", "Mango"},
    ),
    Food(
        name="Apple (1 medium)", food_type="fruit", season_tags={"Autumn", "Winter"},
        dosha_score={"Vata": 1, "Pitta": 1, "Kapha": 1},
        per_serving={"calories": 95, "protein_g": 0.5, "fat_g": 0.3, "carb_g": 25, "sugar_g": 19, "sodium_mg": 2, "satfat_g": 0.1},
        incompatible_with={"Dairy", "Curd (plain, room temp)", "Paneer (fresh)"},
    ),
    Food(
        name="Banana (ripe)", food_type="fruit", season_tags={"All"},
        dosha_score={"Vata": 2, "Pitta": 0, "Kapha": -1},
        per_serving={"calories": 105, "protein_g": 1.3, "fat_g": 0.4, "carb_g": 27, "sugar_g": 14, "sodium_mg": 1, "satfat_g": 0.1},
        incompatible_with={"Milk", "Curd (plain, room temp)"},
    ),
    Food(
        name="Soaked Almonds (10)", food_type="nut", season_tags={"LateWinter", "EarlyWinter", "Autumn"},
        dosha_score={"Vata": 2, "Pitta": 1, "Kapha": 0},
        per_serving={"calories": 70, "protein_g": 3, "fat_g": 6, "carb_g": 2, "sugar_g": 1, "sodium_mg": 0, "satfat_g": 0.6},
    ),
    Food(
        name="Lean Fish Curry", food_type="meat", season_tags={"Winter", "LateWinter"},
        dosha_score={"Vata": 1, "Pitta": 0, "Kapha": 1},
        per_serving={"calories": 240, "protein_g": 26, "fat_g": 12, "carb_g": 6, "sugar_g": 3, "sodium_mg": 480, "satfat_g": 3},
        incompatible_with={"Milk", "Curd (plain, room temp)", "Paneer (fresh)"},
    ),
    Food(
        name="Jeera Rice", food_type="grain", season_tags={"All"},
        dosha_score={"Vata": 2, "Pitta": 1, "Kapha": 0},
        per_serving={"calories": 230, "protein_g": 4.5, "fat_g": 4, "carb_g": 42, "sugar_g": 0.5, "sodium_mg": 280, "satfat_g": 0.8},
    ),
    Food(
        name="Turmeric Milk (golden)", food_type="beverage", season_tags={"LateWinter", "EarlyWinter"},
        dosha_score={"Vata": 3, "Pitta": -1, "Kapha": -1},
        per_serving={"calories": 160, "protein_g": 8, "fat_g": 7, "carb_g": 16, "sugar_g": 12, "sodium_mg": 120, "satfat_g": 4},
        incompatible_with={"Fish", "Citrus Fruits", "Mango"},
    ),
    Food(
        name="Lemon Rice", food_type="grain", season_tags={"Summer", "Spring"},
        dosha_score={"Vata": 0, "Pitta": 1, "Kapha": 0},
        per_serving={"calories": 260, "protein_g": 5, "fat_g": 6, "carb_g": 46, "sugar_g": 1, "sodium_mg": 420, "satfat_g": 1},
        incompatible_with={"Curd (plain, room temp)", "Paneer (fresh)", "Milk"},
    ),
    Food(
        name="Masala Oats (veg)", food_type="grain", season_tags={"All"},
        dosha_score={"Vata": 1, "Pitta": 1, "Kapha": 0},
        per_serving={"calories": 300, "protein_g": 9, "fat_g": 6, "carb_g": 52, "sugar_g": 2, "sodium_mg": 380, "satfat_g": 1.5},
    ),
    Food(
        name="Khichu (steamed rice flour)", food_type="grain", season_tags={"Monsoon"},
        dosha_score={"Vata": 2, "Pitta": 1, "Kapha": 0},
        per_serving={"calories": 220, "protein_g": 4, "fat_g": 2, "carb_g": 46, "sugar_g": 1, "sodium_mg": 350, "satfat_g": 0.4},
    ),
]

# Normalize season tags: treat "All" as all seasons
ALL_SEASONS = {"Summer", "Monsoon", "Autumn", "EarlyWinter", "LateWinter", "Winter", "Spring"}
for f in FOODS:
    if "All" in f.season_tags:
        f.season_tags = set(ALL_SEASONS)

# Build quick lookups
FOOD_INDEX = {f.name: i for i, f in enumerate(FOODS)}

# Some canonical Ayurveda-inspired incompatible pairs (applied across catalog by name substrings)
PAIRING_RULES = [
    ("Milk", "Fish"),
    ("Milk", "Citrus"),
    ("Curd", "Fish"),
    ("Curd", "Citrus"),
    ("Fruit", "Dairy"),
]


def name_matches(token: str, food: Food) -> bool:
    return token.lower() in food.name.lower()


# Expand per-food incompatible_with using generic rules
for f in FOODS:
    for a, b in PAIRING_RULES:
        if name_matches(a, f):
            for g in FOODS:
                if name_matches(b, g):
                    f.incompatible_with.add(g.name)


# -------------------------------
# Optimization model
# -------------------------------

def plan_week(user: Dict, foods: List[Food]) -> Tuple[pd.DataFrame, Dict]:
    dom = user["dominant_dosha"]
    if isinstance(dom, str):
        dom = [dom]
    season = user["season"]
    tgt = user["targets"]
    max_items = int(user.get("max_items_per_meal", 2))
    gap = int(user.get("min_repeat_gap_days", 2))

    # Create MILP
    prob = pulp.LpProblem("AyurvedicWeeklyPlan", pulp.LpMinimize)

    # Variables
    # x[d, m, i] = number of half-servings of food i in day d meal m; integer >=0
    # y[d, m, i] = 1 if food i used in day d meal m
    x = {}
    y = {}
    for d in range(7):
        for m in range(len(MEALS)):
            for i, f in enumerate(foods):
                x[(d, m, i)] = pulp.LpVariable(f"x_{d}_{m}_{i}", lowBound=0, cat=pulp.LpInteger)
                y[(d, m, i)] = pulp.LpVariable(f"y_{d}_{m}_{i}", lowBound=0, upBound=1, cat=pulp.LpBinary)

    # Limit items per meal
    for d in range(7):
        for m in range(len(MEALS)):
            prob += pulp.lpSum(y[(d, m, i)] for i in range(len(foods))) <= max_items

    # Link x and y (0.5 serving granularity)
    BIG_M = 8  # allows up to 4 servings per item per meal (since x counts half servings)
    for d in range(7):
        for m in range(len(MEALS)):
            for i in range(len(foods)):
                prob += x[(d, m, i)] <= BIG_M * y[(d, m, i)]

    # Incompatibility constraints per meal
    name_to_idx = {f.name: idx for idx, f in enumerate(foods)}
    for d in range(7):
        for m in range(len(MEALS)):
            for i, f in enumerate(foods):
                for bad in f.incompatible_with:
                    if bad in name_to_idx:
                        j = name_to_idx[bad]
                        prob += y[(d, m, i)] + y[(d, m, j)] <= 1

    # Anti-repeat within gap days for exact same dish (any meal)
    for i in range(len(foods)):
        for d in range(7):
            for h in range(1, gap + 1):
                if d + h < 7:
                    prob += pulp.lpSum(y[(d, m, i)] for m in range(len(MEALS))) + \
                            pulp.lpSum(y[(d + h, m, i)] for m in range(len(MEALS))) <= 1

    # Daily nutrient totals and deviation variables
    # Deviation from calorie target (absolute value linearization)
    dev_plus = [pulp.LpVariable(f"dev_cal_plus_{d}", lowBound=0) for d in range(7)]
    dev_minus = [pulp.LpVariable(f"dev_cal_minus_{d}", lowBound=0) for d in range(7)]

    # Macro ranges
    cal_lo = (1 - tgt["calorie_tolerance"]) * tgt["calories"]
    cal_hi = (1 + tgt["calorie_tolerance"]) * tgt["calories"]

    macro_tol = tgt["macro_tolerance"]

    def meal_sum(d, nutrient):
        return pulp.lpSum(
            (x[(d, m, i)] * 0.5) * foods[i].per_serving[nutrient]
            for m in range(len(MEALS)) for i in range(len(foods))
        )

    for d in range(7):
        cal_d = meal_sum(d, "calories")
        # absolute deviation
        prob += cal_d - tgt["calories"] == dev_plus[d] - dev_minus[d]
        # Hard bounds (keep within range if feasible)
        prob += cal_d >= cal_lo
        prob += cal_d <= cal_hi

        # Macro soft bounds as inequalities (range)
        for macro in ["protein_g", "fat_g", "carb_g"]:
            prob += meal_sum(d, macro) >= (1 - macro_tol) * tgt[macro]
            prob += meal_sum(d, macro) <= (1 + macro_tol) * tgt[macro]

        # Upper limits (sugar, sodium, satfat)
        prob += meal_sum(d, "sugar_g") <= tgt["sugar_g"]
        prob += meal_sum(d, "sodium_mg") <= tgt["sodium_mg"]
        prob += meal_sum(d, "satfat_g") <= tgt["satfat_g"]

    # Objective: minimize (calorie deviation + penalties) - (season/dosha bonuses)
    season_bonus = []
    dosha_bonus = []
    sugar_penalty = []
    satfat_penalty = []
    sodium_penalty = []

    for d in range(7):
        for m in range(len(MEALS)):
            for i, f in enumerate(foods):
                # Bonuses per *presence* (y), scaled by modest weights
                season_match = 1.0 if season in f.season_tags else 0.0
                season_bonus.append(-0.4 * season_match * y[(d, m, i)])  # negative because we minimize

                ds = 0
                for dd in dom:
                    ds += f.dosha_score.get(dd, 0)
                dosha_bonus.append(-0.3 * ds * y[(d, m, i)])

                # Penalties per *quantity* (x half-servings)
                sugar_penalty.append(0.02 * (x[(d, m, i)] * 0.5) * f.per_serving["sugar_g"])
                satfat_penalty.append(0.04 * (x[(d, m, i)] * 0.5) * f.per_serving["satfat_g"])
                sodium_penalty.append(0.0003 * (x[(d, m, i)] * 0.5) * f.per_serving["sodium_mg"])

    obj = (
        pulp.lpSum(dev_plus) + pulp.lpSum(dev_minus)
        + pulp.lpSum(sugar_penalty) + pulp.lpSum(satfat_penalty) + pulp.lpSum(sodium_penalty)
        + pulp.lpSum(season_bonus) + pulp.lpSum(dosha_bonus)
    )

    prob += obj

    # Solve
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    # Build result tables
    rows = []
    for d, day in enumerate(DAYS):
        for m, meal in enumerate(MEALS):
            picks = []
            for i, f in enumerate(foods):
                qty_half = int(pulp.value(x[(d, m, i)]) or 0)
                if qty_half > 0:
                    picks.append((f.name, qty_half * 0.5))
            rows.append({"day": day, "meal": meal, "items": picks})

    plan_df = pd.DataFrame(rows)

    # Daily nutrition summary
    nut_rows = []
    for d, day in enumerate(DAYS):
        summary = {k: 0.0 for k in NUTRIENTS}
        for m in range(len(MEALS)):
            for i, f in enumerate(foods):
                qty_half = float(pulp.value(x[(d, m, i)]) or 0.0) * 0.5
                if qty_half > 0:
                    for k in NUTRIENTS:
                        summary[k] += qty_half * f.per_serving[k]
        summary.update({"day": day, "cal_dev": float(pulp.value(dev_plus[d] + dev_minus[d]))})
        nut_rows.append(summary)
    nut_df = pd.DataFrame(nut_rows)[["day"] + NUTRIENTS + ["cal_dev"]]

    return plan_df, {"nutrition": nut_df, "status": pulp.LpStatus[prob.status], "objective": pulp.value(prob.objective)}


# -------------------------------
# Pretty printing
# -------------------------------

def pretty_print(plan_df: pd.DataFrame, extras: Dict):
    # Expand items for display
    display_rows = []
    for day in DAYS:
        for meal in MEALS:
            items = plan_df[(plan_df["day"] == day) & (plan_df["meal"] == meal)]["items"].values[0]
            if items:
                txt = "; ".join([f"{name} (x{qty:.1f} serving)" for name, qty in items])
            else:
                txt = "—"
            display_rows.append([day, meal.title(), txt])

    print("\n=== Weekly Plan ===")
    print(tabulate(display_rows, headers=["Day", "Meal", "Items"], tablefmt="github"))

    print("\n=== Daily Nutrition (sum) ===")
    nut = extras["nutrition"].copy()
    print(tabulate(nut, headers="keys", tablefmt="github", floatfmt=".1f"))

    print("\nStatus:", extras["status"])
    print("Objective:", f"{extras['objective']:.2f}")


# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":
    plan, extras = plan_week(USER_PROFILE, FOODS)
    pretty_print(plan, extras)

    # Tip: to export as CSVs
    # plan.to_csv("weekly_plan.csv", index=False)
    # extras["nutrition"].to_csv("daily_nutrition_summary.csv", index=False)
