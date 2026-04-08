#!/usr/bin/env python3
"""
Production-Ready Ingredient Mapper
Use this in your project to map food ingredients to nutrition database

Usage:
    from ingredient_mapper import IngredientMapper
    
    mapper = IngredientMapper('ingredient_mapping.csv')
    
    # Map a single ingredient
    nutrition_ing = mapper.map_ingredient('Tomato')
    
    # Check if recipe has all ingredients
    recipe_ingredients = ['Tomato', 'Onion', 'Garlic', 'Water', 'Salt']
    is_complete = mapper.recipe_has_complete_nutrition(recipe_ingredients)
    
    # Get nutrition ingredient or None
    for food_ing in recipe_ingredients:
        nutr_ing = mapper.get_nutrition_ingredient(food_ing)
        if nutr_ing:
            print(f"{food_ing} -> {nutr_ing}")
"""

import pandas as pd
from typing import Optional, List, Dict, Tuple

class IngredientMapper:
    def __init__(self, mapping_csv_path: str = 'ingredient_mapping.csv'):
        """
        Initialize the mapper with the mapping CSV file
        
        Args:
            mapping_csv_path: Path to ingredient_mapping.csv
        """
        self.mapping_df = pd.read_csv(mapping_csv_path)
        
        # Create lookup dictionary for fast access
        self.mapping = {}
        for _, row in self.mapping_df.iterrows():
            food_ing = row['food_ingredient']
            
            if row['status'] == 'MATCHED':
                self.mapping[food_ing] = {
                    'nutrition_ingredient': row['nutrition_ingredient'],
                    'confidence': row['confidence'],
                    'method': row['match_method'],
                    'status': 'MATCHED',
                    'ignorable': False
                }
            elif row['status'] == 'IGNORABLE':
                self.mapping[food_ing] = {
                    'nutrition_ingredient': None,
                    'confidence': 1.0,
                    'method': 'ignorable',
                    'status': 'IGNORABLE',
                    'ignorable': True
                }
            else:  # UNMATCHED
                self.mapping[food_ing] = {
                    'nutrition_ingredient': None,
                    'confidence': row['confidence'] if pd.notna(row['confidence']) else 0.0,
                    'method': None,
                    'status': 'UNMATCHED',
                    'ignorable': False
                }
        
        # Statistics
        self.stats = {
            'total': len(self.mapping),
            'matched': len([m for m in self.mapping.values() if m['status'] == 'MATCHED']),
            'ignorable': len([m for m in self.mapping.values() if m['status'] == 'IGNORABLE']),
            'unmatched': len([m for m in self.mapping.values() if m['status'] == 'UNMATCHED'])
        }
    
    def get_nutrition_ingredient(self, food_ingredient: str, 
                                 min_confidence: float = 0.0) -> Optional[str]:
        """
        Get the nutrition database ingredient name for a food ingredient
        
        Args:
            food_ingredient: Ingredient name from food/recipe dataset
            min_confidence: Minimum confidence score to accept (0.0-1.0)
        
        Returns:
            Nutrition database ingredient name or None if not found/low confidence
        """
        if food_ingredient not in self.mapping:
            return None
        
        entry = self.mapping[food_ingredient]
        
        # Ignorable ingredients return None
        if entry['ignorable']:
            return None
        
        # Unmatched ingredients return None
        if entry['status'] == 'UNMATCHED':
            return None
        
        # Check confidence threshold
        if entry['confidence'] < min_confidence:
            return None
        
        return entry['nutrition_ingredient']
    
    def is_ignorable(self, food_ingredient: str) -> bool:
        """Check if ingredient is ignorable (zero nutritional value)"""
        if food_ingredient not in self.mapping:
            return False
        return self.mapping[food_ingredient]['ignorable']
    
    def is_matched(self, food_ingredient: str) -> bool:
        """Check if ingredient has a valid match"""
        if food_ingredient not in self.mapping:
            return False
        return self.mapping[food_ingredient]['status'] == 'MATCHED'
    
    def get_match_info(self, food_ingredient: str) -> Optional[Dict]:
        """
        Get complete information about a match
        
        Returns:
            Dictionary with nutrition_ingredient, confidence, method, status
            or None if ingredient not found
        """
        return self.mapping.get(food_ingredient)
    
    def recipe_has_complete_nutrition(self, recipe_ingredients: List[str],
                                     min_confidence: float = 0.75) -> Tuple[bool, Dict]:
        """
        Check if a recipe has complete nutrition data available
        
        Args:
            recipe_ingredients: List of ingredient names from recipe
            min_confidence: Minimum confidence threshold for matches
        
        Returns:
            (is_complete, details_dict)
            - is_complete: True if ALL ingredients are either matched or ignorable
            - details_dict: Breakdown of matched, ignorable, unmatched counts
        """
        matched = []
        ignorable = []
        unmatched = []
        low_confidence = []
        
        for ing in recipe_ingredients:
            if ing not in self.mapping:
                unmatched.append(ing)
                continue
            
            entry = self.mapping[ing]
            
            if entry['ignorable']:
                ignorable.append(ing)
            elif entry['status'] == 'MATCHED':
                if entry['confidence'] >= min_confidence:
                    matched.append(ing)
                else:
                    low_confidence.append((ing, entry['confidence']))
            else:
                unmatched.append(ing)
        
        is_complete = len(unmatched) == 0 and len(low_confidence) == 0
        
        details = {
            'total_ingredients': len(recipe_ingredients),
            'matched': len(matched),
            'ignorable': len(ignorable),
            'unmatched': len(unmatched),
            'low_confidence': len(low_confidence),
            'is_complete': is_complete,
            'unmatched_list': unmatched,
            'low_confidence_list': low_confidence
        }
        
        return is_complete, details
    
    def filter_complete_recipes(self, recipes_df: pd.DataFrame, 
                                ingredient_column: str = 'ingredients',
                                separator: str = ',',
                                min_confidence: float = 0.75) -> pd.DataFrame:
        """
        Filter a DataFrame of recipes to only those with complete nutrition data
        
        Args:
            recipes_df: DataFrame with recipes
            ingredient_column: Name of column containing ingredients
            separator: Separator used in ingredients list (e.g., ',' or ';')
            min_confidence: Minimum confidence threshold
        
        Returns:
            Filtered DataFrame with only complete recipes
        """
        def check_complete(ingredients_str):
            if pd.isna(ingredients_str):
                return False
            
            ingredients = [ing.strip() for ing in str(ingredients_str).split(separator)]
            is_complete, _ = self.recipe_has_complete_nutrition(ingredients, min_confidence)
            return is_complete
        
        return recipes_df[recipes_df[ingredient_column].apply(check_complete)]
    
    def get_mapping_for_recipe(self, recipe_ingredients: List[str],
                              min_confidence: float = 0.75) -> Dict[str, Optional[str]]:
        """
        Get mapping dictionary for all ingredients in a recipe
        
        Args:
            recipe_ingredients: List of ingredient names
            min_confidence: Minimum confidence threshold
        
        Returns:
            Dictionary: {food_ingredient: nutrition_ingredient or None}
        """
        result = {}
        for ing in recipe_ingredients:
            result[ing] = self.get_nutrition_ingredient(ing, min_confidence)
        return result
    
    def print_statistics(self):
        """Print summary statistics"""
        print("="*70)
        print("INGREDIENT MAPPING STATISTICS")
        print("="*70)
        print(f"Total Food Ingredients: {self.stats['total']}")
        print(f"  - Matched: {self.stats['matched']} ({self.stats['matched']/self.stats['total']*100:.1f}%)")
        print(f"  - Ignorable: {self.stats['ignorable']} ({self.stats['ignorable']/self.stats['total']*100:.1f}%)")
        print(f"  - Unmatched: {self.stats['unmatched']} ({self.stats['unmatched']/self.stats['total']*100:.1f}%)")
        print("="*70)
        actionable = self.stats['total'] - self.stats['ignorable']
        actionable_match_rate = self.stats['matched'] / actionable * 100
        print(f"Actionable Match Rate: {actionable_match_rate:.1f}%")
        print("="*70)


# Example usage
if __name__ == "__main__":
    print("Ingredient Mapper - Example Usage\n")
    
    # Initialize mapper
    mapper = IngredientMapper('ingredient_mapping.csv')
    
    # Print stats
    mapper.print_statistics()
    
    # Example 1: Map single ingredient
    print("\nExample 1: Map single ingredient")
    print("-"*70)
    test_ingredients = ['Tomato', 'Onion', 'Garlic', 'Water', 'Cinnamon']
    for ing in test_ingredients:
        nutr_ing = mapper.get_nutrition_ingredient(ing)
        info = mapper.get_match_info(ing)
        if nutr_ing:
            print(f"✓ {ing:20} -> {nutr_ing:40} ({info['confidence']:.2f})")
        elif mapper.is_ignorable(ing):
            print(f"○ {ing:20} -> IGNORABLE (no nutrition impact)")
        else:
            print(f"✗ {ing:20} -> NOT FOUND")
    
    # Example 2: Check recipe completeness
    print("\n\nExample 2: Check recipe completeness")
    print("-"*70)
    
    recipe1 = ['Tomato', 'Onion', 'Garlic', 'Water', 'Salt', 'Turmeric powder', 'Oil']
    recipe2 = ['Tomato', 'Onion', 'Bread', 'Cheese', 'Mayonnaise']
    
    for i, recipe in enumerate([recipe1, recipe2], 1):
        print(f"\nRecipe {i}: {', '.join(recipe)}")
        is_complete, details = mapper.recipe_has_complete_nutrition(recipe)
        print(f"  Complete: {'YES ✓' if is_complete else 'NO ✗'}")
        print(f"  Matched: {details['matched']}")
        print(f"  Ignorable: {details['ignorable']}")
        print(f"  Unmatched: {details['unmatched']}")
        if details['unmatched_list']:
            print(f"  Missing: {', '.join(details['unmatched_list'])}")
    
    # Example 3: Get full mapping for a recipe
    print("\n\nExample 3: Full recipe mapping")
    print("-"*70)
    recipe = ['Milk', 'Sugar', 'Rice', 'Cardamom', 'Water']
    mapping = mapper.get_mapping_for_recipe(recipe)
    
    print(f"Recipe: {', '.join(recipe)}\n")
    print(f"{'Food Ingredient':<20} -> {'Nutrition Ingredient':<40}")
    print("-"*70)
    for food_ing, nutr_ing in mapping.items():
        if nutr_ing:
            print(f"{food_ing:<20} -> {nutr_ing:<40}")
        elif mapper.is_ignorable(food_ing):
            print(f"{food_ing:<20} -> [IGNORABLE]")
        else:
            print(f"{food_ing:<20} -> [NOT FOUND]")
