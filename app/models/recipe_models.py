from pydantic import BaseModel, Field
from typing import List, Dict, Optional

class SimpleRecipe(BaseModel):
    name: str
    cal: int
    prot: int
    fat: int
    sugar: int

class MealChoice(SimpleRecipe):
    vata_score: Optional[int] = None
    pitta_score: Optional[int] = None
    kapha_score: Optional[int] = None
    alternatives: Optional[List[SimpleRecipe]] = None
class DayMeals(BaseModel):
    breakfast: List[MealChoice] = Field(default_factory=list)
    lunch: List[MealChoice] = Field(default_factory=list)
    snacks: List[MealChoice] = Field(default_factory=list)
    dinner: List[MealChoice] = Field(default_factory=list)

class FinalDayMeals(BaseModel):
    breakfast: MealChoice= Field(default_factory=MealChoice)
    lunch: MealChoice = Field(default_factory=MealChoice)
    snacks: MealChoice = Field(default_factory=MealChoice)
    dinner:  MealChoice= Field(default_factory=MealChoice)


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

class IngredientListResponse(BaseModel):
    favor_ingredients: List[str]
    avoid_ingredients: List[str]
# Pydantic models for Recipe/Ingredient schemas
