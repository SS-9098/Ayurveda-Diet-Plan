import random
import DailyNutrients
# -----------------------------
# Dummy Food Database
# -----------------------------
food_db = [
    {"name": "Oats with almond milk", "calories": 350, "protein": 12, "carbs": 60, "fat": 9, "dosha": ["pitta↓", "vata↓"]},
    {"name": "Moong dal khichdi", "calories": 450, "protein": 18, "carbs": 75, "fat": 8, "dosha": ["all"]},
    {"name": "Apple with almonds", "calories": 200, "protein": 5, "carbs": 25, "fat": 8, "dosha": ["pitta↓"]},
    {"name": "Barley vegetable soup", "calories": 300, "protein": 10, "carbs": 40, "fat": 6, "dosha": ["pitta↓", "kapha↓"]},
    {"name": "Poha with peas", "calories": 320, "protein": 9, "carbs": 65, "fat": 5, "dosha": ["vata↓"]},
    {"name": "Brown rice + mung dal", "calories": 500, "protein": 20, "carbs": 85, "fat": 7, "dosha": ["all"]},
    {"name": "Pear with seeds", "calories": 220, "protein": 4, "carbs": 30, "fat": 9, "dosha": ["pitta↓"]},
    {"name": "Vegetable stew + chapati", "calories": 400, "protein": 12, "carbs": 55, "fat": 10, "dosha": ["vata↓", "pitta↓"]},
    {"name": "Idli with chutney", "calories": 330, "protein": 9, "carbs": 65, "fat": 4, "dosha": ["pitta↓"]},
    {"name": "Millet roti + sabzi", "calories": 480, "protein": 15, "carbs": 80, "fat": 9, "dosha": ["kapha↓"]},
    {"name": "Fruit smoothie", "calories": 300, "protein": 7, "carbs": 55, "fat": 5, "dosha": ["pitta↓"]},
    {"name": "Vegetable upma", "calories": 350, "protein": 8, "carbs": 65, "fat": 6, "dosha": ["all"]},
    {"name": "Dalia (wheat porridge)", "calories": 340, "protein": 10, "carbs": 68, "fat": 5, "dosha": ["pitta↓"]},
]

RecommendedDailyIntake = DailyNutrients.getRecommendedDailyIntake()

# -----------------------------
# Utility Functions
# -----------------------------
def filter_foods(dosha, meal_type):
    """Filter foods suitable for dosha and meal type."""
    return [f for f in food_db if (dosha in f["dosha"] or "all" in f["dosha"])]

def pick_meal(candidates, target_cal):
    """Pick closest calorie meal."""
    return min(candidates, key=lambda f: abs(f["calories"] - target_cal))

# -----------------------------
# Daily Plan Generator
# -----------------------------
def generate_daily_plan(calories, dosha):
    distribution = {"breakfast": 0.2, "lunch": 0.4, "snack": 0.15, "dinner": 0.25}
    plan = {}

    for meal_type, frac in distribution.items():
        candidates = filter_foods(dosha, meal_type)
        if not candidates:
            continue
        target_cal = calories * frac
        plan[meal_type] = pick_meal(candidates, target_cal)
    return plan

# -----------------------------
# Weekly Plan Generator
# -----------------------------
def generate_weekly_plan(calories, dosha):
    weekly_plan = []
    used_meals = set()

    for day in range(7):
        day_plan = generate_daily_plan(calories, dosha)

        # Ensure variety (avoid repeats more than twice)
        for meal_type, meal in day_plan.items():
            if meal["name"] in used_meals:
                alternatives = [f for f in filter_foods(dosha, meal_type) if f["name"] not in used_meals]
                if alternatives:
                    day_plan[meal_type] = random.choice(alternatives)
            used_meals.add(day_plan[meal_type]["name"])

        weekly_plan.append(day_plan)

    return weekly_plan

# -----------------------------
# Example Run
# -----------------------------
user_dosha = "kapha↓"   # Example: Pitta-dominant user
user_calories = 1800

plan = generate_weekly_plan(user_calories, user_dosha)

# Display output
for i, day in enumerate(plan, 1):
    print(f"\nDay {i} Plan:")
    for meal_type, meal in day.items():
        print(f"  {meal_type.capitalize()}: {meal['name']} ({meal['calories']} kcal)")
