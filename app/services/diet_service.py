from app.db.database import get_collection
from app.models.account_models import BiologicalData
import random

# Caches to hold data in memory for high performance
INGREDIENTS_CACHE = {}
RECIPES_CACHE = []


def preload_caches():
    """Loads all ingredients and recipes from DB into memory on startup."""
    print("Preloading ingredients and recipes into cache...")
    ingredients_coll = get_collection("ingredients")
    for doc in ingredients_coll.find({}, {"name": 1, "category": 1, "dosha_info": 1, "_id": 0}):
        INGREDIENTS_CACHE[doc['name'].lower()] = doc

    recipes_coll = get_collection("recipes")
    for doc in recipes_coll.find({}):
        # Ensure all required fields exist to prevent runtime errors
        if 'normalized_ingredients' in doc and 'nutrition_per_serving' in doc:
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
    """Calculates estimated daily caloric needs using the Harris-Benedict Equation."""
    if bio_data.gender == "male":
        bmr = 88.362 + (13.397 * bio_data.weight_kg) + (4.799 * bio_data.height_cm) - (5.677 * bio_data.age)
    else:  # female
        bmr = 447.593 + (9.247 * bio_data.weight_kg) + (3.098 * bio_data.height_cm) - (4.330 * bio_data.age)

    activity_multipliers = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9}
    calories = bmr * activity_multipliers[bio_data.activity_level]

    return {"calories": round(calories)}


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

