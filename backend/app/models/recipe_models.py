from pydantic import BaseModel, Field
from typing import List, Dict

# --- Ingredient Models ---
class IngredientDoshaInfo(BaseModel):
    status: str
    notes: str | None = None

class IngredientInDB(BaseModel):
    name: str
    category: str
    dosha_info: Dict[str, List[IngredientDoshaInfo]]

# --- Recipe Models ---
class DoshaProfile(BaseModel):
    vata_score: int
    pitta_score: int
    kapha_score: int

class NutritionInfo(BaseModel):
    calories: float
    fat_g: float
    saturated_fat_g: float
    cholesterol_mg: float
    sodium_mg: float
    carbohydrate_g: float
    fiber_g: float
    sugar_g: float
    protein_g: float

class RecipePublic(BaseModel):
    id: str = Field(alias="_id")
    name: str
    ingredients: List[str]
    instructions: str
    dosha_profile: DoshaProfile
    nutrition_per_serving: NutritionInfo

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
# Pydantic models for Recipe/Ingredient schemas
