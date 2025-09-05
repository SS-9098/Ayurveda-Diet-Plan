from app.db.database import get_collection
from app.models.account_models import BiologicalData
import random
from app.core.config import settings

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


def generate_recipe_plan(patient_profile: dict) -> dict:
    """Generates a 7-day recipe plan for a patient."""
    if not patient_profile.get('biological_data'):
        return {"error": "Biological data is required to generate a recipe plan."}

    daily_needs = calculate_daily_needs(BiologicalData(**patient_profile['biological_data']))

    favor_ingredients_lower = {ing.lower() for ing in patient_profile.get('approved_favor_ingredients', [])}
    avoid_ingredients_lower = {ing.lower() for ing in patient_profile.get('approved_avoid_ingredients', [])}

    suitable_recipes = []
    for recipe in RECIPES_CACHE:
        # The recipe's ingredients must be a subset of the 'favor' list
        # and must not have any intersection with the 'avoid' list.
        recipe_ing_lower = {ing.lower() for ing in recipe['normalized_ingredients']}
        if recipe_ing_lower.issubset(favor_ingredients_lower) and not recipe_ing_lower.intersection(
                avoid_ingredients_lower):
            suitable_recipes.append(recipe)

    if len(suitable_recipes) < 3:  # Need at least 3 recipes for a day's plan
        return {"error": "Not enough suitable recipes found in the database to generate a full plan."}

    plan = {}
    for day in range(1, 8):
        random.shuffle(suitable_recipes)
        # Simple selection of 3 random recipes for the day
        day_recipes = suitable_recipes[:4]
        total_calories = sum(r['nutrition_per_serving']['calories'] for r in day_recipes)
        plan[f"Day {day}"] = {
            "Breakfast": day_recipes[0]['name'],
            "Lunch": day_recipes[1]['name'],
            "Snack": day_recipes[3]['name'],
            "Dinner": day_recipes[2]['name'],
            "Estimated Calories": round(total_calories),
            "Target Calories": daily_needs['calories']
        }
    return plan

