from app.db.database import get_collection
from app.models.account_models import BiologicalData
from app.core.config import settings
from app.services.OR_Model import generate_meal_plan
from pathlib import Path

# Caches to hold data in memory for high performance
INGREDIENTS_CACHE = {}
RECIPES_CACHE = []


async def preload_caches(app):

    """Loads all ingredients and recipes from DB into memory on startup."""
    print("Preloading ingredients and recipes into cache...")
    db = app.state.mongo_client[settings.AYUSHMITRA]

    ingredients_coll = db["food_ingredients"]
    cursor = ingredients_coll.find({}, {"name": 1, "category": 1, "dosha_info": 1, "_id": 0})
    async for doc in cursor:
        INGREDIENTS_CACHE[doc['name'].lower()] = doc

    recipes_coll = db["food_recipes"]
    cursor = recipes_coll.find({})
    async for doc in cursor:
        # Ensure all required fields exist to prevent runtime errors
        if 'ingredients' in doc and 'nutrition_per_serving' in doc:
            RECIPES_CACHE.append(doc)
    print(f"Cached {len(INGREDIENTS_CACHE)} ingredients and {len(RECIPES_CACHE)} recipes.")


def generate_ingredient_list(dosha: str, allergies: list[str]) -> dict:
    """Generates the initial list of favor/avoid ingredients for a patient."""
    favor_list, avoid_list = set(), set()
    doshas_to_check = dosha.lower().split('-')

    for ing_name, ing_data in INGREDIENTS_CACHE.items():
        is_allergic = any(allergy.lower() in ing_data.get('category', '').lower() for allergy in allergies)
        if is_allergic:
            avoid_list.add(ing_data['name'])
            continue

        for d in doshas_to_check:
            dosha_key = d.capitalize()
            if dosha_key in ing_data.get('dosha_info', {}):
                statuses = {info['status'] for info in ing_data['dosha_info'][dosha_key]}
                if "Avoid" in statuses:
                    avoid_list.add(ing_data['name'])
                elif "Favor" in statuses:
                    favor_list.add(ing_data['name'])

    return {"favor_ingredients": sorted(list(favor_list - avoid_list)), "avoid_ingredients": sorted(list(avoid_list))}


def calculate_daily_needs(bio_data: BiologicalData) -> dict:
    """
    Calculates estimated daily nutritional needs including calories, protein, carbs, fats, and sugar limit.
    This function now integrates all necessary calculations based on standard guidelines.
    """

    def _calculate_calories(bio_data: BiologicalData) -> float:
        """Calculates TDEE using the Harris-Benedict Equation."""
        if bio_data.gender == "male":
            bmr = 88.362 + (13.397 * bio_data.weight_kg) + (4.799 * bio_data.height_cm) - (5.677 * bio_data.age)
        else:  # female
            bmr = 447.593 + (9.247 * bio_data.weight_kg) + (3.098 * bio_data.height_cm) - (4.330 * bio_data.age)

        activity_multipliers = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9}
        tdee = bmr * activity_multipliers[bio_data.activity_level]
        return tdee

    def _calculate_protein_g(weight_kg: float, activity_level: str) -> float:
        """Calculates protein needs based on DRI, adjusted for activity."""
        protein_multipliers = {"sedentary": 0.8, "light": 1.0, "moderate": 1.2, "active": 1.4, "very_active": 1.6}
        return weight_kg * protein_multipliers[activity_level]

    def _calculate_macro_avg_g(total_calories: float, percent_range: tuple[float, float],
                               calories_per_gram: int) -> float:
        """Calculates the average grams for a macronutrient based on a percentage of total calories."""
        # Calculate the average of the percentage range (e.g., (0.20 + 0.35) / 2 = 0.275 for fat)
        avg_percent = (percent_range[0] + percent_range[1]) / 2
        avg_g = (total_calories * avg_percent) / calories_per_gram
        return avg_g

    # 1. Calculate Total Daily Calories (TDEE)
    total_calories = _calculate_calories(bio_data)

    # 2. Calculate Protein (g)
    protein_g = _calculate_protein_g(bio_data.weight_kg, bio_data.activity_level)

    # 3. Calculate Average Fat (g) - based on an average of the 20-35% range
    fat_g_avg = _calculate_macro_avg_g(total_calories, (0.20, 0.35), 9)

    # 4. Calculate Average Carbohydrate (g) - based on an average of the 45-65% range
    carbs_g_avg = _calculate_macro_avg_g(total_calories, (0.45, 0.65), 4)

    # 5. Calculate Added Sugar Limit (g) - based on <10% of total calories
    added_sugar_g_limit = (total_calories * 0.10) / 4

    # Combine all results into a single response object with average values
    return {
        "calories_kcal": round(total_calories),
        "protein_g": round(protein_g),
        "fat_g_avg": round(fat_g_avg),
        "carbohydrate_g_avg": round(carbs_g_avg),
        "added_sugar_g_limit": round(added_sugar_g_limit)
    }


def generate_recipe_plan_options(patient_profile: dict) -> dict:
    """Generates a 7-day recipe plan with alternatives for a patient using the OR_Model solver."""
    if not patient_profile.get('biological_data'):
        return {"error": "Biological data is required to generate a recipe plan."}

    daily_needs = patient_profile.get('daily_needs')
    user_profile = {
        "cal": int(daily_needs['calories_kcal']),
        "prot": int(daily_needs['protein_g']),
        "fat": int(daily_needs['fat_g_avg']),
        "sugar": int(daily_needs['added_sugar_g_limit']),
        "dosha": patient_profile.get('dosha_result', 'Vata'),
        "nuts": False, "diary": False, "veg": False, "vegan": False
    }

    csv_setting = getattr(settings, 'FOOD_RECIPES_CSV', 'food_recipies.csv')
    csv_path = Path(csv_setting)
    if not csv_path.is_file():
        csv_path = Path(__file__).resolve().parent / csv_setting
    if not csv_path.is_file():
        return {"error": f"Solver error: CSV file not found at {csv_setting} or {csv_path}"}

    try:
        solver_plan = generate_meal_plan(csv_path=str(csv_path), user_profile=user_profile)
        return solver_plan
    except Exception as e:
        return {"error": f"Solver error: {str(e)}"}


def format_finalized_plan_for_pdf(finalized_plan: dict, daily_needs: dict) -> dict:
    """Formats a finalized recipe plan from the database into the structure needed for the PDF report."""
    plan = {}
    # The finalized_plan from DB will have day keys like '1', '2', etc.
    for day_key, slots in finalized_plan.items():
        if not day_key.isdigit():  # Skip metadata like _id or patient_id
            continue

        day_label = f"Day {day_key}"
        plan[day_label] = {}

        # In the finalized plan, each slot has one chosen meal object
        for slot_name, meal in slots.items():
            slot_label = slot_name.capitalize()
            plan[day_label][slot_label] = meal.get('name') if meal else "Not specified"

        # Calculate estimated calories from the chosen meals for the day
        try:
            est_cal = sum(meal.get('cal', 0) for meal in slots.values() if meal)
        except Exception:
            est_cal = 0
        plan[day_label]["Estimated Calories"] = round(est_cal)
        plan[day_label]["Target Calories"] = daily_needs.get('calories_kcal', 0)

    return plan


