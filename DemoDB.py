from dataclasses import dataclass
from typing import List, Dict, Set
import pandas as pd


@dataclass
class Food:
    name: str
    food_type: str
    season_tags: Set[str]
    dosha_score: Dict[str, int]
    per_serving: Dict[str, float]
    incompatible_with: Set[str]


# Convert DataFrame to list of Food objects
foods_list = []

# Load the large food dataset
def ya():
    df_foods = pd.read_csv('ayurvedic_food_dataset_large.csv')

    # Check the first few rows
    print(df_foods.head())
    import ast

    # Convert season_tags and incompatible_with from string to list
    df_foods['season_tags'] = df_foods['season_tags'].apply(ast.literal_eval)
    df_foods['incompatible_with'] = df_foods['incompatible_with'].apply(ast.literal_eval)


    for _, row in df_foods.iterrows():
        foods_list.append(
            Food(
                name=row['name'],
                food_type=row['type'],
                season_tags=set(row['season_tags']),
                dosha_score={'Vata': row['Vata'], 'Pitta': row['Pitta'], 'Kapha': row['Kapha']},
                per_serving={
                    'calories': row['calories'],
                    'protein_g': row['protein_g'],
                    'fat_g': row['fat_g'],
                    'carb_g': row['carb_g'],
                    'sugar_g': row['sugar_g'],
                    'sodium_mg': row['sodium_mg'],
                    'satfat_g': row['satfat_g'],
                },
                incompatible_with=set(row['incompatible_with'])
            )
        )

def getData():
    ya()
    return foods_list