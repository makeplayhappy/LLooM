import os
import pandas as pd
from collections import defaultdict
import re

def clean_thread_column(text):
    # Remove non-ASCII characters
    text = re.sub(r'[^\x00-\x7F]+', '', text)
    # Remove newlines
    text = text.replace('\n', ' ').replace('\r', '')
    # Remove quotes
    text = text.replace('"', '')
    #.replace("'", "")
    # Replace multiple spaces with a single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def combine_csv_files(folder_path, story_keys):
    combined_data = {key: defaultdict(list) for key in story_keys}
    max_entries = {key: 0 for key in story_keys}
    
    csv_files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]
    
    for file in csv_files:
        file_path = os.path.join(folder_path, file)
        df = pd.read_csv(file_path)
        
        # Clean the 'Thread' column
        if 'Thread' in df.columns:
            df['Thread'] = df['Thread'].astype(str).apply(clean_thread_column)
        
        file_prefix = os.path.splitext(file)[0]
        df_filtered = df[df['Story_Key'].isin(story_keys)]
        
        for key in story_keys:
            key_data = df_filtered[df_filtered['Story_Key'] == key]
            num_entries = len(key_data)
            max_entries[key] = max(max_entries[key], num_entries)
            
            for col in df.columns:
                if col != 'Story_Key':
                    combined_data[key][f'{file_prefix} {col}'].extend(key_data[col].tolist())
    
    # Pad shorter lists with None values
    for key in story_keys:
        for col in combined_data[key]:
            current_length = len(combined_data[key][col])
            if current_length < max_entries[key]:
                combined_data[key][col].extend([None] * (max_entries[key] - current_length))
    
    # Create and save combined DataFrames for each Story_Key
    for key in story_keys:
        if combined_data[key]:
            result_df = pd.DataFrame(combined_data[key])
            result_df.insert(0, 'Story_Key', [key] * len(result_df))
            output_file = f'{key}_combined.csv'
            result_df.to_csv(output_file, index=False, quoting=1)  # quoting=1 to quote all fields
            print(f"Combined data for '{key}' saved as '{output_file}'")
        else:
            print(f"No data found for Story_Key: '{key}'")

# Specify the folder path containing your CSV files
folder_path = 'csv'

# List of Story_Keys to filter
story_keys = ["alice_and_james", "it_was_after", "his_body_was", "once_upon_a", "in_the_age"]

# Run the function to combine CSV files
combine_csv_files(folder_path, story_keys)
