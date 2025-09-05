# Save as meal_planner_ayurveda.py
# Run with Python 3.9+
# Requires: pip install ortools scikit-learn pandas

from ortools.sat.python import cp_model
import pandas as pd
import time

# ------------------
# 1) Load food database
# ------------------

def load_foods(csv_path):
    df = pd.read_csv(csv_path)

    foods = []
    for i, row in df.iterrows():
        if i > 2000:
            break
        if int(row['cal']) == 0:
            continue
        foods.append({
            "id": int(row["recipe_id"]),
            "name": row["name"],
            "cal": int(row["cal"]) or 0,
            "prot": int(row["prot"]) or 0,
            "fat": int(row["fat"]) or 0,
            "carb": int(row["carb"]) or 0,
            "sugar": int(row["sugar"]) or 0,
            "allowed_slots": ["breakfast", "lunch", "snack", "dinner"],
            "incompatible_with": [],
            "vata_score": float(row["vata_score"]) or 0,
            "pitta_score": float(row["pitta_score"]) or 0,
            "kapha_score": float(row["kapha_score"]) or 0,
        })
    return foods


FOODS = load_foods("food_recipies.csv")
FOOD_BY_ID = {f["id"]: f for f in FOODS}
N_F = len(FOODS)
print(f"Loaded {N_F} recipes from CSV")

DAYS = list(range(7))
SLOTS = ["breakfast", "lunch", "snack", "dinner"]

# ------------------
# 2) User targets
# ------------------
user_daily_targets = {
    "cal": 2000,   # kcal
    "prot": 75,    # grams
    "fat": 60,     # grams
    "sugar": 30,   # grams
}

# tolerances (±)
cal_tol = int(user_daily_targets["cal"] * 0.1)     # 10%
prot_tol = int(user_daily_targets["prot"] * 0.2)   # 20%
fat_tol = int(user_daily_targets["fat"] * 0.25)    # 25%
sugar_tol = int(user_daily_targets["sugar"] * 0.25)

user_dosha = "Vata"
max_repeats_per_week = 2

# ------------------
# 3) Build CP-SAT model
# ------------------
model = cp_model.CpModel()

x = {}
for f in range(N_F):
    for d in DAYS:
        for s in range(len(SLOTS)):
            x[(f, d, s)] = model.NewBoolVar(f"x_f{f}_d{d}_s{s}")

# Only allowed slots
for f_idx, food in enumerate(FOODS):
    allowed = set(food["allowed_slots"])
    for d in DAYS:
        for s_idx, sname in enumerate(SLOTS):
            if sname not in allowed:
                model.Add(x[(f_idx, d, s_idx)] == 0)

# At least 1, at most 3 items per slot
for d in DAYS:
    for s_idx in range(len(SLOTS)):
        model.Add(sum(x[(f, d, s_idx)] for f in range(N_F)) >= 1)
        model.Add(sum(x[(f, d, s_idx)] for f in range(N_F)) <= 3)

# Limit repeats
for f in range(N_F):
    model.Add(sum(x[(f, d, s)] for d in DAYS for s in range(len(SLOTS))) <= max_repeats_per_week)

# Nutrition constraints per day
for d in DAYS:
    total_cal = sum(FOODS[f]["cal"] * x[(f, d, s)] for f in range(N_F) for s in range(len(SLOTS)))
    total_prot = sum(FOODS[f]["prot"] * x[(f, d, s)] for f in range(N_F) for s in range(len(SLOTS)))
    total_fat = sum(FOODS[f]["fat"] * x[(f, d, s)] for f in range(N_F) for s in range(len(SLOTS)))
    total_sugar = sum(FOODS[f]["sugar"] * x[(f, d, s)] for f in range(N_F) for s in range(len(SLOTS)))

    model.Add(total_cal >= user_daily_targets["cal"] - cal_tol)
    model.Add(total_cal <= user_daily_targets["cal"] + cal_tol)
    model.Add(total_prot >= user_daily_targets["prot"] - prot_tol)
    model.Add(total_prot <= user_daily_targets["prot"] + prot_tol)
    model.Add(total_fat >= user_daily_targets["fat"] - fat_tol)
    model.Add(total_fat <= user_daily_targets["fat"] + fat_tol)
    model.Add(total_sugar >= user_daily_targets["sugar"] - sugar_tol)
    model.Add(total_sugar <= user_daily_targets["sugar"] + sugar_tol)

# Dosha preference scoring
dosha_score_terms = []
for f_idx, food in enumerate(FOODS):
    if user_dosha == "Vata":
        score = food["vata_score"]
    elif user_dosha == "Pitta":
        score = food["pitta_score"]
    elif user_dosha == "Kapha":
        score = food["kapha_score"]
    else:
        score = 0
    for d in DAYS:
        for s in range(len(SLOTS)):
            if score != 0:
                dosha_score_terms.append(score * x[(f_idx, d, s)])

# Objective: nutrition deviations + dosha rewards
W_CAL, W_PROT, W_FAT, W_SUGAR = 100, 50, 30, 30
W_DOSHA = 50

linear_obj = (
    W_CAL * sum(abs(FOODS[f]["cal"] - user_daily_targets["cal"] / 4) * x[(f, d, s)] for f in range(N_F) for d in DAYS for s in range(len(SLOTS)))
    + W_PROT * sum(abs(FOODS[f]["prot"] - user_daily_targets["prot"] / 4) * x[(f, d, s)] for f in range(N_F) for d in DAYS for s in range(len(SLOTS)))
    + W_FAT * sum(abs(FOODS[f]["fat"] - user_daily_targets["fat"] / 4) * x[(f, d, s)] for f in range(N_F) for d in DAYS for s in range(len(SLOTS)))
    + W_SUGAR * sum(abs(FOODS[f]["sugar"] - user_daily_targets["sugar"] / 4) * x[(f, d, s)] for f in range(N_F) for d in DAYS for s in range(len(SLOTS)))
    - W_DOSHA * sum(dosha_score_terms)
)

model.Minimize(linear_obj)

# ------------------
# 4) Solve
# ------------------
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 30.0
solver.parameters.num_search_workers = 8

print("Running CP-SAT solver (time limit 30s)...")
start = time.time()
res = solver.Solve(model)
end = time.time()

if res == cp_model.OPTIMAL or res == cp_model.FEASIBLE:
    print("\nPlan summary (solved in {:.2f}s):".format(end - start))

    def food_similarity(f1, f2):
        # smaller diff = more similar
        diff = abs(f1["cal"] - f2["cal"]) \
             + abs(f1["prot"] - f2["prot"]) \
             + abs(f1["fat"] - f2["fat"]) \
             + abs(f1["sugar"] - f2["sugar"]) \
             + abs(f1["vata_score"] - f2["vata_score"]) \
             + abs(f1["pitta_score"] - f2["pitta_score"]) \
             + abs(f1["kapha_score"] - f2["kapha_score"])
        return diff

    TOP_K = 4  # number of alternatives per slot

    for d in DAYS:
        chosen = []
        for s_idx, sname in enumerate(SLOTS):
            foods = [FOODS[f] for f in range(N_F) if solver.Value(x[(f, d, s_idx)]) == 1]
            chosen.extend(foods)

        totcal = sum(f["cal"] for f in chosen)
        totprot = sum(f["prot"] for f in chosen)
        totfat = sum(f["fat"] for f in chosen)
        totsugar = sum(f["sugar"] for f in chosen)

        print(f"\nDay {d+1}: cal {totcal}, prot {totprot}g, fat {totfat}g, sugar {totsugar}g")

        for s_idx, sname in enumerate(SLOTS):
            foods = [FOODS[f] for f in range(N_F) if solver.Value(x[(f, d, s_idx)]) == 1]
            if foods:
                print(f"  {sname.capitalize():9}:")
                for chosen_food in foods:
                    print(f"    ✔ {chosen_food['name']} "
                          f"(cal {chosen_food['cal']}, prot {chosen_food['prot']}g, "
                          f"fat {chosen_food['fat']}g, sugar {chosen_food['sugar']}g)"
                          f"dosha scores: Vata {chosen_food['vata_score']}, Pitta {chosen_food['pitta_score']}, Kapha {chosen_food['kapha_score']}")

                    # show alternatives
                    ranked = sorted(FOODS, key=lambda f: food_similarity(f, chosen_food))
                    alts = [f for f in ranked if f["id"] != chosen_food["id"]][:TOP_K]
                    for i, alt in enumerate(alts, 1):
                        print(f"       Option {i}. {alt['name']} "
                              f"(cal {alt['cal']}, prot {alt['prot']}g, "
                              f"fat {alt['fat']}g, sugar {alt['sugar']}g)")
            else:
                print(f"  {sname.capitalize():9}: None")
