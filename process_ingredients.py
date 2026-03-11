import pandas as pd
import os
import re
def clean_val(val):
    if isinstance(val, str):
        if '±' in val:
            return val.split('±')[0]
    return val
def extract_scientific(name_str):
    if not isinstance(name_str, str):
        return str(name_str), ""
    match = re.search(r'\(([^)]+)\)[^()]*$', name_str)
    if match:
        scientific = match.group(1)
        new_name = name_str.replace(f"({scientific})", "").strip()
        return new_name.lower(), scientific
    return name_str.lower(), ""
def main():
    data_dir = "ingredients"
    out_file = "combined_ingredients.csv"
    out_path = os.path.join(data_dir, out_file)
    if os.path.exists(out_path):
        os.remove(out_path)
        print(f"Removed existing {out_path}")
    files = [f for f in os.listdir(data_dir) if f.endswith('.csv') and f != out_file]
    files.sort()
    if not files:
        print("No CSV files found.")
        return
    combined_df = None
    for f in files:
        path = os.path.join(data_dir, f)
        print(f"Processing {f}...")
        try:
            df = pd.read_csv(path)
        except Exception as e:
            print(f"Error reading {f}: {e}")
            continue
        if 'name' not in df.columns or 'code' not in df.columns:
            print(f"Skipping {f} (missing columns)")
            continue
        scientific_names = []
        cleaned_names = []
        for name in df['name']:
             n, s = extract_scientific(name)
             cleaned_names.append(n)
             scientific_names.append(s)
        df['name'] = cleaned_names
        df['scientific_name'] = scientific_names
        id_cols = ['code', 'name', 'regn', 'scientific_name']
        cols_to_clean = [c for c in df.columns if c not in id_cols]
        for c in cols_to_clean:
            df[c] = df[c].apply(clean_val)
        if df['code'].duplicated().any():
            df = df.drop_duplicates(subset='code', keep='first')
        df = df.set_index('code')
        if combined_df is None:
            combined_df = df
        else:
            combined_df = combined_df.combine_first(df)
    if combined_df is not None:
        combined_df = combined_df.reset_index()

        # Clean quotes in 'name' column
        if 'name' in combined_df.columns:
            combined_df['name'] = combined_df['name'].astype(str).str.replace('"', '').str.replace("'", "")

        # Load index.csv for renaming
        index_path = os.path.join("app", "index.csv")
        # Adjust path if script is run from project root and app is in root
        if not os.path.exists(index_path):
             # Try absolute path just in case
             index_path = "/home/pokemon/PycharmProjects/Ayurveda-Diet-Plan/app/index.csv"

        if os.path.exists(index_path):
            try:
                print(f"Loading column mapping from {index_path}...")
                index_df = pd.read_csv(index_path)
                # Create mapping: code -> name
                # Filter out empty codes or names
                index_df = index_df.dropna(subset=['code', 'name'])
                rename_map = dict(zip(index_df['code'], index_df['name']))

                # Apply renaming
                combined_df = combined_df.rename(columns=rename_map)
                print("Renamed columns using app/index.csv")
            except Exception as e:
                print(f"Error loading index map: {e}")
        else:
            print(f"Warning: {index_path} not found. Skipping column renaming.")

        cols = list(combined_df.columns)
        # We need to adjust priority list because columns might have been renamed
        # code -> Food Code (likely), name -> Food Name
        # improved priority checking

        # Check what the new names are for our priority columns
        # code -> Food Code
        # name -> Food Name
        # scientific_name -> Scientific Name
        # regn -> No. of Regions

        # We can just check for "Food Code" or "code"

        # ... existing logic was simple list ...
        # Let's just dump it, the order is less critical than content,
        # but let's try to keep identification first.

        def is_id_col(c):
            c_lower = c.lower()
            return any(x in c_lower for x in ['code', 'name', 'scientific'])

        id_cols = [c for c in cols if is_id_col(c)]
        other_cols = [c for c in cols if c not in id_cols]
        new_order = id_cols + other_cols

        combined_df = combined_df[new_order]

        combined_df.to_csv(out_path, index=False)
        print(f"Created {out_path} with shape {combined_df.shape}")
        bad_cols = [c for c in combined_df.columns if '_x' in c or '_y' in c]
        if bad_cols:
            print(f"WARNING: Bad columns detected: {bad_cols[:5]}...")
    else:
        print("No data.")
if __name__ == "__main__":
    main()
