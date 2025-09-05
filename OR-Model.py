# Save as meal_planner_ayurveda.py
# Run with Python 3.9+
# Requires: pip install ortools scikit-learn pandas

from ortools.sat.python import cp_model
import pandas as pd
import time


# ------------------
# 1) Load food database
# ------------------

def load_foods(csv_path, nuts=False, diary=False, veg=False, vegan=False):
    df = pd.read_csv(csv_path)
    foods = []
    for i, row in df.iterrows():
        if i > 2000:
            break
        if int(row['calories']) == 0:
            continue
        if nuts:
            if row['nuts']:
                continue
        if diary:
            if row['diary']:
                continue
        if veg:
            if row['animal_foods']:
                continue
        if vegan:
            if row['diary'] or row['nuts']:
                continue
        foods.append({
            "id": int(row["recipe_id"]),
            "name": row["name"],
            "cal": int(row["calories"]) or 0,
            "prot": int(row["protein_g"]) or 0,
            "fat": int(row["fat_g"]) or 0,
            "carb": int(row["carbohydrate_g"]) or 0,
            "sugar": int(row["sugar_g"]) or 0,
            "allowed_slots": [row["slots"]],
            "incompatible_with": [],
            "vata_score": float(row["vata_score"]) or 0,
            "pitta_score": float(row["pitta_score"]) or 0,
            "kapha_score": float(row["kapha_score"]) or 0,
        })
    return foods

# ------------------
# 2) Meal planner function
# ------------------

def generate_meal_plan(csv_path,
                       user_profile=None,
                       max_repeats_per_week=2,
                       solver_time_limit=30):
    """
    Generates a 7-day Ayurvedic meal plan.

    Returns:
        dict: {day: {slot: [chosen foods with nutrition]}}
    """
    if user_profile is None:
        user_profile = {"cal": 2000,
                        "prot": 75,
                        "fat": 60,
                        "sugar": 30,
                        "dosha": "Vata",
                        "nuts": False,
                        "diary": False,
                        "veg": False,
                        "vegan": False}

    user_dosha = user_profile["dosha"]

    FOODS = load_foods(csv_path)
    FOOD_BY_ID = {f["id"]: f for f in FOODS}
    N_F = len(FOODS)

    DAYS = list(range(7))
    SLOTS = ["breakfast", "lunch", "snack", "dinner"]

    # tolerances (±)
    cal_tol = int(user_profile["cal"] * 0.1)
    prot_tol = int(user_profile["prot"] * 0.2)
    fat_tol = int(user_profile["fat"] * 0.25)
    sugar_tol = int(user_profile["sugar"] * 0.25)

    # ------------------
    # Build CP-SAT model
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

        model.Add(total_cal >= user_profile["cal"] - cal_tol)
        model.Add(total_cal <= user_profile["cal"] + cal_tol)
        model.Add(total_prot >= user_profile["prot"] - prot_tol)
        model.Add(total_prot <= user_profile["prot"] + prot_tol)
        model.Add(total_fat >= user_profile["fat"] - fat_tol)
        model.Add(total_fat <= user_profile["fat"] + fat_tol)
        model.Add(total_sugar >= user_profile["sugar"] - sugar_tol)
        model.Add(total_sugar <= user_profile["sugar"] + sugar_tol)

    # Dosha preference scoring
    dosha_score_terms = []
    for f_idx, food in enumerate(FOODS):
        score = food.get(f"{user_dosha.lower()}_score", 0)
        for d in DAYS:
            for s in range(len(SLOTS)):
                if score != 0:
                    dosha_score_terms.append(score * x[(f_idx, d, s)])

    # Objective: nutrition deviations + dosha rewards
    W_CAL, W_PROT, W_FAT, W_SUGAR, W_DOSHA = 100, 50, 30, 30, 50
    linear_obj = (
        W_CAL * sum(abs(FOODS[f]["cal"] - user_profile["cal"] / 4) * x[(f, d, s)]
                    for f in range(N_F) for d in DAYS for s in range(len(SLOTS))) +
        W_PROT * sum(abs(FOODS[f]["prot"] - user_profile["prot"] / 4) * x[(f, d, s)]
                     for f in range(N_F) for d in DAYS for s in range(len(SLOTS))) +
        W_FAT * sum(abs(FOODS[f]["fat"] - user_profile["fat"] / 4) * x[(f, d, s)]
                    for f in range(N_F) for d in DAYS for s in range(len(SLOTS))) +
        W_SUGAR * sum(abs(FOODS[f]["sugar"] - user_profile["sugar"] / 4) * x[(f, d, s)]
                      for f in range(N_F) for d in DAYS for s in range(len(SLOTS))) -
        W_DOSHA * sum(dosha_score_terms)
    )

    model.Minimize(linear_obj)

    # ------------------
    # Solve
    # ------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = solver_time_limit
    solver.parameters.num_search_workers = 8

    start = time.time()
    res = solver.Solve(model)
    end = time.time()

    if res not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return {"error": "No feasible solution found."}

    # ------------------
    # Format results
    # ------------------
    def food_similarity(f1, f2):
        diff = abs(f1["cal"] - f2["cal"]) \
             + abs(f1["prot"] - f2["prot"]) \
             + abs(f1["fat"] - f2["fat"]) \
             + abs(f1["sugar"] - f2["sugar"]) \
             + abs(f1["vata_score"] - f2["vata_score"]) \
             + abs(f1["pitta_score"] - f2["pitta_score"]) \
             + abs(f1["kapha_score"] - f2["kapha_score"])
        return diff

    TOP_K = 4
    plan = {}
    for d in DAYS:
        plan[d+1] = {}
        for s_idx, sname in enumerate(SLOTS):
            foods = [FOODS[f] for f in range(N_F) if solver.Value(x[(f, d, s_idx)]) == 1]
            slot_list = []
            for chosen_food in foods:
                slot_list.append({
                    "name": chosen_food["name"],
                    "cal": chosen_food["cal"],
                    "prot": chosen_food["prot"],
                    "fat": chosen_food["fat"],
                    "sugar": chosen_food["sugar"],
                    "vata_score": chosen_food["vata_score"],
                    "pitta_score": chosen_food["pitta_score"],
                    "kapha_score": chosen_food["kapha_score"],
                    "alternatives": [
                        {
                            "name": alt["name"],
                            "cal": alt["cal"],
                            "prot": alt["prot"],
                            "fat": alt["fat"],
                            "sugar": alt["sugar"],
                        } for alt in sorted(FOODS, key=lambda f: food_similarity(f, chosen_food)) if alt["id"] != chosen_food["id"]][:TOP_K]
                })
            plan[d+1][sname] = slot_list
    plan["solver_time_sec"] = end - start
    return plan


# ------------------
# Run as main
# ------------------
if __name__ == "__main__":
    csv_file = "food_recipies.csv"
    meal_plan = generate_meal_plan(csv_file)
    for day, slots in meal_plan.items():
        if day == "solver_time_sec":
            print(f"\nSolver finished in {slots:.2f}s")
            continue
        print(f"\nDay {day}:")
        for slot, foods in slots.items():
            if not foods:
                print(f"  {slot.capitalize():9}: None")
            else:
                print(f"  {slot.capitalize():9}:")
                for f in foods:
                    print(f"    ✔ {f['name']} "
                          f"(cal {f['cal']}, prot {f['prot']}g, fat {f['fat']}g, sugar {f['sugar']}g)")
                    for i, alt in enumerate(f["alternatives"], 1):
                        print(f"       Option {i}. {alt['name']} "
                              f"(cal {alt['cal']}, prot {alt['prot']}g, fat {alt['fat']}g, sugar {alt['sugar']}g)")
