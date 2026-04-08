import pandas as pd
import numpy as np
import re

# 1. Load your datasets
df_recipes = pd.read_csv('your_754_recipes.csv')
df_units = pd.read_csv('Units.xlsx - Sheet1.csv')  # INDB unit mappings

# 2. Clean the Units file (Since it has duplicate column names in the raw CSV)
# Looking at the snippet, column 0 is Food, 1 is Unit, 2 is Grams/Ml
df_units.columns = ['Food_Item', 'Unit_Measure', 'Gram_Equivalent', 'Remarks', 'Source']

# Keep only rows that actually have a gram/ml equivalent
df_units = df_units.dropna(subset=['Gram_Equivalent'])


# Extract just the numbers from "115g" or "240ml" using regex
def extract_numeric_weight(val):
    match = re.search(r'([\d.]+)', str(val))
    return float(match.group(1)) if match else None


df_units['Gram_Float'] = df_units['Gram_Equivalent'].apply(extract_numeric_weight)

# Clean strings for matching (lowercase and strip spaces)
df_units['Food_Item'] = df_units['Food_Item'].str.lower().str.strip()
df_units['Unit_Measure'] = df_units['Unit_Measure'].str.lower().str.strip()

# 3. Define our Fallback Dictionary (for missing items)
fallback_dict = {
    'g': 1.0,
    'ml': 1.0,
    'tsp': 5.0,
    'tbsp': 15.0,
    'c': 240.0,
    'sprig': 2.0,
    'nos': 50.0,
    'pinch': 0.3,
    'cubes': 15.0  # e.g., Ice cubes
}


# 4. Create the Conversion Function
def convert_to_grams(row):
    food = str(row['food_name']).lower().strip()
    unit = str(row['unit']).lower().strip()
    amount = float(row['amount'])

    # Base case: Already in grams or ml
    if unit in ['g', 'ml']:
        return amount

    # Step A: Check INDB specific database (Match exact food AND unit)
    specific_match = df_units[(df_units['Food_Item'] == food) & (df_units['Unit_Measure'].str.contains(unit, na=False))]
    if not specific_match.empty:
        # We found a specific density conversion! (e.g., 1 cup nuts = 115g)
        gram_per_unit = specific_match['Gram_Float'].values[0]
        # BUT wait! INDB's "Gram_Equivalent" is usually the weight of ONE unit.
        # So we multiply amount by the INDB's exact weight.
        return amount * gram_per_unit

    # Step B: Check standard INDB general volume conversions (where food item is blank)
    general_match = df_units[df_units['Food_Item'].isna() & (df_units['Unit_Measure'].str.contains(unit, na=False))]
    if not general_match.empty:
        gram_per_unit = general_match['Gram_Float'].values[0]
        return amount * gram_per_unit

    # Step C: Fallback to our hardcoded dictionary
    if unit in fallback_dict:
        return amount * fallback_dict[unit]

    # If all fails, assume 1:1 to avoid breaking the code, but flag it
    print(f"Warning: Unknown unit '{unit}' for food '{food}'. Defaulting to 1:1 multiplier.")
    return amount


# 5. Apply the conversion to your recipes!
df_recipes['weight_in_grams'] = df_recipes.apply(convert_to_grams, axis=1)

print("Unit Normalization Complete!")
print(df_recipes[['recipe_name', 'food_name', 'amount', 'unit', 'weight_in_grams']].head(10))