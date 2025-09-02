# Save as meal_planner_ayurveda.py and run with Python 3.9+.
# Requires: pip install ortools scikit-learn pandas

from ortools.sat.python import cp_model
import random
import math
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import pandas as pd
import ast

# ------------------
# 1) Example food database (extend with real dataset or CSV)
# ------------------
# Each food entry fields:
# - id, name
# - calories, protein_g, fat_g, carbs_g, sugar_g (integers)
# - allowed_slots: list of ['breakfast','lunch','snack','dinner']
# - dosha_tags: list of dosha(s) that this food pacifies or is suitable for e.g. ['Vata'] or ['neutral']
# - incompatible_with: list of other food ids that should not be in the same meal (e.g. fruit+dairy)
#
# NOTE: In a production system use a CSV that includes ingredients; the ML classifier below can be trained on ingredients -> dosha labels.


def load_foods(csv_path):
    df = pd.read_csv(csv_path)

    foods = []
    for i, row in df.iterrows():
        foods.append({
            "id": i,
            "name": row["name"],
            "cal": int(row["cal"]),
            "prot": int(row["prot"]),
            "fat": int(row["fat"]),
            "carb": int(row["carb"]),
            "sugar": int(row["sugar"]),
            "allowed_slots": ["breakfast","lunch","snack","dinner"],
            "incompatible_with": ast.literal_eval(row["incompatible_with"]),
            #"ingredients": row["ingredients"],
            "vata_score": float(row["vata_score"]),
            "pitta_score": float(row["pitta_score"]),
            "kapha_score": float(row["kapha_score"]),
        })
    for food in foods:
        new_incompat = []
        for other in food["incompatible_with"]:
            if isinstance(other, str) and other.isdigit():
                other = int(other)
            if isinstance(other, int) and other in id_to_idx:
                new_incompat.append(id_to_idx[other])
        food["incompatible_with"] = new_incompat
    return foods

FOODS = load_foods("ayurvedic_food_dataset_large.csv")
FOOD_BY_ID = {f["id"]: f for f in FOODS}
N_F = len(FOODS)
print(f"Loaded {N_F} foods from CSV")


DAYS = list(range(7))
SLOTS = ["breakfast","lunch","snack","dinner"]
slot_index = {s:i for i,s in enumerate(SLOTS)}

# ------------------
# 2) Tiny ML: ingredients -> dosha classifier (optional)
#    (In a real project you'd train on a large labeled dataset.)
# ------------------
def train_tiny_dosha_classifier(food_list):
    texts = [f["ingredients"] for f in food_list]
    # For labels pick primary dosha label (if multiple, pick first or 'neutral')
    labels = [ (f["dosha_tags"][0] if f["dosha_tags"] else "neutral") for f in food_list ]

    vect = TfidfVectorizer(ngram_range=(1,2))
    X = vect.fit_transform(texts)
    clf = LogisticRegression(max_iter=500)
    clf.fit(X, labels)
    print("Trained tiny dosha classifier on", len(texts), "examples.")
    return vect, clf

# Train classifier (optional)
#vectorizer, dosha_clf = train_tiny_dosha_classifier(FOODS)

# Function to predict dosha for a new food ingredient string
# def predict_dosha_for_ingredients(ingredient_text):
#     X = vectorizer.transform([ingredient_text])
#     pred = dosha_clf.predict(X)[0]
#     # Return predicted primary dosha
#     return pred

# ------------------
# 3) User targets & preferences
# ------------------
user_daily_targets = {
    "cal": 2000,   # kcal
    "prot": 75,    # grams
    "fat": 60,     # grams
    "sugar": 30,   # grams
}

# tolerance fraction (allowed +/-)
tolerance = 0.12  # 12% tolerance on calories/macros

# user's dominant dosha (used to prefer foods that pacify that dosha)
user_dosha = "Vata"  # could be Vata, Pitta, Kapha, or None/neutral

# max repeats of same food per week
max_repeats_per_week = 2

# ------------------
# 4) Build CP-SAT model
# ------------------
model = cp_model.CpModel()

# Binary decision vars x[f,d,s] = 1 if food f selected on day d in slot s
x = {}
for f in range(N_F):
    for d in DAYS:
        for s in range(len(SLOTS)):
            x[(f,d,s)] = model.NewBoolVar(f"x_f{f}_d{d}_s{s}")

# Constraint: only select foods in allowed slots
for f_idx, food in enumerate(FOODS):
    allowed = set(food["allowed_slots"])
    for d in DAYS:
        for s_idx, sname in enumerate(SLOTS):
            if sname not in allowed:
                model.Add(x[(f_idx,d,s_idx)] == 0)

# Constraint: exactly one item per slot per day (or you can relax to at-least-one)
for d in DAYS:
    for s_idx in range(len(SLOTS)):
        # you may want to allow multiple small items per slot; here we pick exactly 1 dish per slot.
        model.Add(sum(x[(f,d,s_idx)] for f in range(N_F)) <= 2)

# Constraint: variety - limit repeats of same food across week
for f in range(N_F):
    model.Add(sum(x[(f,d,s)] for d in DAYS for s in range(len(SLOTS))) <= max_repeats_per_week)

# Constraint: incompatibilities — no pair that are incompatible may appear in same meal (same day+slot)
for f in range(N_F):
    incompatible = FOOD_BY_ID[f]["incompatible_with"]
    if not incompatible:
        continue
    for d in DAYS:
        for s in range(len(SLOTS)):
            for other_id in incompatible:
                # can't have both f and other_id in same day+slot
                model.Add(x[(f,d,s)] + x[(other_id,d,s)] <= 1)

# Macro sum per day
# We'll create integer scaled sums (all grams / kcal are integers already)
# For CP-SAT objective use deviations: create int variables for positive and negative deviation
max_dev_cal = int(user_daily_targets["cal"] * 2)  # generous bound
max_dev_macro = 500  # arbitrary bound for protein/fat/sugar dev

dev_cal_pos = {}
dev_cal_neg = {}
dev_prot_pos = {}
dev_prot_neg = {}
dev_fat_pos = {}
dev_fat_neg = {}
dev_sugar_pos = {}
dev_sugar_neg = {}

for d in DAYS:
    dev_cal_pos[d] = model.NewIntVar(0, max_dev_cal, f"dev_cal_pos_{d}")
    dev_cal_neg[d] = model.NewIntVar(0, max_dev_cal, f"dev_cal_neg_{d}")
    dev_prot_pos[d] = model.NewIntVar(0, max_dev_macro, f"dev_prot_pos_{d}")
    dev_prot_neg[d] = model.NewIntVar(0, max_dev_macro, f"dev_prot_neg_{d}")
    dev_fat_pos[d] = model.NewIntVar(0, max_dev_macro, f"dev_fat_pos_{d}")
    dev_fat_neg[d] = model.NewIntVar(0, max_dev_macro, f"dev_fat_neg_{d}")
    dev_sugar_pos[d] = model.NewIntVar(0, max_dev_macro, f"dev_sugar_pos_{d}")
    dev_sugar_neg[d] = model.NewIntVar(0, max_dev_macro, f"dev_sugar_neg_{d}")

    # compute sums
    cal_sum = sum(FOODS[f]["cal"] * x[(f,d,s)] for f in range(N_F) for s in range(len(SLOTS)))
    prot_sum = sum(FOODS[f]["prot"] * x[(f,d,s)] for f in range(N_F) for s in range(len(SLOTS)))
    fat_sum = sum(FOODS[f]["fat"] * x[(f,d,s)] for f in range(N_F) for s in range(len(SLOTS)))
    sugar_sum = sum(FOODS[f]["sugar"] * x[(f,d,s)] for f in range(N_F) for s in range(len(SLOTS)))

    # target
    tcal = user_daily_targets["cal"]
    tprot = user_daily_targets["prot"]
    tfat = user_daily_targets["fat"]
    tsugar = user_daily_targets["sugar"]

    # dev >= sum - target and dev >= target - sum
    model.Add(cal_sum - tcal <= dev_cal_pos[d])
    model.Add(tcal - cal_sum <= dev_cal_neg[d])

    model.Add(prot_sum - tprot <= dev_prot_pos[d])
    model.Add(tprot - prot_sum <= dev_prot_neg[d])

    model.Add(fat_sum - tfat <= dev_fat_pos[d])
    model.Add(tfat - fat_sum <= dev_fat_neg[d])

    model.Add(sugar_sum - tsugar <= dev_sugar_pos[d])
    model.Add(tsugar - sugar_sum <= dev_sugar_neg[d])

# Ayurvedic preference: encourage foods that pacify the user's dosha
# Create per-assignment reward var and maximize total dosha-score (we'll combine in minimization objective by negative weight)
user_dosha = "Vata"  # or "Pitta", "Kapha"

dosha_score_terms = []
for f_idx, food in enumerate(FOODS):
    if user_dosha == "Vata":
        score = food["vata_score"]
    elif user_dosha == "Pitta":
        score = food["pitta_score"]
    elif user_dosha == "Kapha":
        score = food["kapha_score"]
    else:
        score = 0  # neutral if not specified

    for d in DAYS:
        for s in range(len(SLOTS)):
            if score != 0:
                dosha_score_terms.append(score * x[(f_idx,d,s)])

# Objective: minimize weighted sum of deviations minus weight * dosha_matches
# We need integer weights. Choose weights to balance priorities.
W_CAL = 15
W_PROT = 3
W_FAT = 6
W_SUGAR = 6
W_DOSHA = 10   # reward for dosha-balancing food (we'll subtract from cost)

# Build objective expression
obj_terms = []
for d in DAYS:
    obj_terms.append(W_CAL * (dev_cal_pos[d] + dev_cal_neg[d]))
    obj_terms.append(W_PROT * (dev_prot_pos[d] + dev_prot_neg[d]))
    obj_terms.append(W_FAT * (dev_fat_pos[d] + dev_fat_neg[d]))
    obj_terms.append(W_SUGAR * (dev_sugar_pos[d] + dev_sugar_neg[d]))

# subtract dosha matches (i.e., reward)
# CP-SAT only supports minimization; to reward, we subtract (so lower cost when more matches)
# Build sum of x for dosha matches
dosha_match_sum = sum(dosha_score_terms)
# Since objective must be integer linear, we add a term -W_DOSHA * dosha_match_sum
# but CP-SAT objective is minimization of linear expression -> add negative coefficients by adding model.NewIntVar? No — we can add terms with negative coefficient directly via model.Minimize(...).
# We'll compose final expression as linear_expr = sum(obj_terms) - W_DOSHA * dosha_match_sum

from ortools.sat.python import cp_model as cp

linear_obj = sum(obj_terms) - W_DOSHA * sum(dosha_score_terms)
model.Minimize(linear_obj)

# ------------------
# 5) Solve
# ------------------
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 30.0
solver.parameters.num_search_workers = 8

res = solver.Solve(model)

if res == cp_model.OPTIMAL or res == cp_model.FEASIBLE:
    print("Solution found. Objective:", solver.ObjectiveValue())
    # Construct weekly plan
    plan = {d: {s: None for s in SLOTS} for d in DAYS}
    for d in DAYS:
        for s_idx, sname in enumerate(SLOTS):
            for f in range(N_F):
                if solver.Value(x[(f, d, s_idx)]) == 1:
                    plan[d][sname] = FOODS[f]

    # print plan
    for d in DAYS:
        print(f"\nDay {d+1}:")
        # compute day totals
        totcal = sum(FOODS[f]["cal"] * solver.Value(x[(f, d, s_idx)]) for f in range(N_F) for s_idx in range(len(SLOTS)))
        totprot = sum(FOODS[f]["prot"] * solver.Value(x[(f, d, s_idx)]) for f in range(N_F) for s_idx in range(len(SLOTS)))
        totfat = sum(FOODS[f]["fat"] * solver.Value(x[(f, d, s_idx)]) for f in range(N_F) for s_idx in range(len(SLOTS)))
        totsugar = sum(FOODS[f]["sugar"] * solver.Value(x[(f, d, s_idx)]) for f in range(N_F) for s_idx in range(len(SLOTS)))
        print(f"  Totals — cal: {totcal}, prot: {totprot}g, fat: {totfat}g, sugar: {totsugar}g")

        for s in SLOTS:
            food = plan[d][s]
            if food:
                print(
                    f"    {s.capitalize():9}: {food['name']} "
                    f"(cal {food['cal']}, prot {food['prot']}g, fat {food['fat']}g, sugar {food['sugar']}g, "
                    f"V:{food['vata_score']}, P:{food['pitta_score']}, K:{food['kapha_score']})"
                )
            else:
                print(f"    {s.capitalize():9}: None")
else:
    print("No solution found. Status:", res)


# ------------------
# 6) How you can extend / productionize
# ------------------
#
# - Replace FOODS with a full CSV having: id,name,ingredients,cal,prot,fat,carb,sugar,allowed_slots,dosha_tags,incompatible_ids,seasonality
# - Expand ML classifier: label thousands of foods with dosha tags (expert-labeled). Use the ingredient text + simple features (cooked/raw, heating quality, taste: sweet/sour/pungent) and train a multi-label model.
# - Use constraints for Ayurvedic combinatorics: e.g., disallow raw fruit after heavy meals; avoid certain food pairings (fish+milk etc). Encode them as incompatibilities.
# - Add user-specific constraints: allergies, vegetarian/vegan, meal-skipping preferences, religious restrictions.
# - Make objective multi-criteria and allow parametrization of tolerance (e.g., athlete vs sedentary).
# - Consider splitting slots into multiple items (allow two smaller items) by changing the "exactly 1 per slot" constraint to ">=1 or <= K" and using portion-sizes (integer multiples).
#
# Tips for real macros:
# - Scale quantities to integers (grams) if you add portion sizing variables.
# - If you need target ranges rather than exact closeness, add linear inequality constraints instead of deviation variables.
