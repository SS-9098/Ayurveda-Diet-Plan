from app.db.database import get_collection
from app.models.account_models import BiologicalData
import random

# --- Preload caches on startup for performance ---
INGREDIENTS_CACHE = {}
RECIPES_CACHE = []


def preload_caches():
    print("Preloading ingredients and recipes into cache...")
    # Cache ingredients
    ingredients_coll = get_collection("INGREDIENTS")
    for doc in ingredients_coll.find({}, {"name": 1, "category": 1, "dosha_info": 1, "_id": 0}):
        INGREDIENTS_CACHE[doc['name'].lower()] = doc

    # Cache recipes
    recipes_coll = get_collection("RECIPES")
    for doc in recipes_coll.find({}):
        RECIPES_CACHE.append(doc)
    print(f"Cached {len(INGREDIENTS_CACHE)} ingredients and {len(RECIPES_CACHE)} recipes.")


def generate_ingredient_list(dosha: str, allergies: list[str]) -> dict:
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
    # Harris-Benedict Equation for BMR
    if bio_data.gender == "male":
        bmr = 88.362 + (13.397 * bio_data.weight_kg) + (4.799 * bio_data.height_cm) - (5.677 * bio_data.age)
    else:  # female
        bmr = 447.593 + (9.247 * bio_data.weight_kg) + (3.098 * bio_data.height_cm) - (4.330 * bio_data.age)

    activity_multipliers = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9}
    calories = bmr * activity_multipliers[bio_data.activity_level]

    return {"calories": round(calories), "protein_g": round(calories * 0.15 / 4)}


def generate_recipe_plan(patient_profile: dict) -> dict:
    daily_needs = calculate_daily_needs(BiologicalData(**patient_profile['biological_data']))

    favor_ingredients = set(patient_profile.get('approved_favor_ingredients', []))
    avoid_ingredients = set(patient_profile.get('approved_avoid_ingredients', []))

    # Filter suitable recipes
    suitable_recipes = []
    for recipe in RECIPES_CACHE:
        ingredients_set = set(ing.lower() for ing in recipe['ingredients'])
        if ingredients_set.issubset(favor_ingredients) and not ingredients_set.intersection(avoid_ingredients):
            suitable_recipes.append(recipe)

    # Simple greedy algorithm for 7-day plan
    plan = {}
    if not suitable_recipes: return {"error": "Not enough suitable recipes found."}

    for day in range(1, 8):
        random.shuffle(suitable_recipes)
        plan[f"Day {day}"] = {
            "Breakfast": suitable_recipes[0]['name'],
            "Lunch": suitable_recipes[1]['name'],
            "Dinner": suitable_recipes[2]['name'],
            "Estimated Calories": round(suitable_recipes[0]['nutrition_per_serving']['calories'] +
                                        suitable_recipes[1]['nutrition_per_serving']['calories'] +
                                        suitable_recipes[2]['nutrition_per_serving']['calories']),
            "Target Calories": daily_needs['calories']
        }
    return plan
# Logic for generating ingredient/recipe lists
