# import pandas as pd
#
# # Load your new dataset
# df = pd.read_csv('combined_ingredients_modified.csv')
#
# # Create a "Full Description" for the LLM to read
# # Format: "Ingredient Name (Specific Detail)"
# # Example: "wheat flour (refined)", "wheat flour (atta)"
# df['llm_query_string'] = df['food_name'] + " (" + df['food_details'].fillna('raw/whole') + ")"
#
# # Print the list to copy-paste
# print("COPY THIS LIST FOR YOUR PROMPT:\n")
# for item in df['llm_query_string'].unique():
#     print(item)

import re

# Read the raw file
with open('usable/ingredients_ayurveda', 'r') as f:
    raw_data = f.read()

# 1. FIX NEWLINES: Look for the pattern where a number ends and text begins
# Pattern: Digit (0, 1, or -1) followed by Space followed by Text
# We replace that Space with a Newline
cleaned_data = re.sub(r'(-?1|0) ([a-zA-Z])', r'\1\n\2', raw_data)

# 2. FIX COMMAS: Quote the names
# We split by newline, then look for the FIRST comma.
# Everything before the first comma is the name. We wrap it in quotes.
final_lines = []
lines = cleaned_data.split('\n')
header = lines[0]  # Keep header as is
final_lines.append(header)

for line in lines[1:]:
    if not line.strip(): continue

    # Split the line into Name vs Values
    # We assume the name is everything before the FIRST comma followed by a digit
    match = re.match(r'^(.*?)(,(-?1|0),.*)$', line)
    if match:
        name = match.group(1).strip()
        values = match.group(2)  # Includes the leading comma

        # If name has comma, wrap in quotes
        if ',' in name:
            name = f'"{name}"'

        final_lines.append(f"{name}{values}")
    else:
        # Fallback if regex fails
        final_lines.append(line)

# Save to proper CSV
with open('usable/cleaned_ingredients.csv', 'w') as f:
    f.write('\n'.join(final_lines))

print("Fixed! Saved as 'cleaned_ingredients.csv'")