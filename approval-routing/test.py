from fuzzywuzzy import fuzz
import pandas as pd
import logging

def compare(file):
    # Load the CSV files
    df1 = pd.read_csv('./Archieves/Yooz CC Import_v3.csv', delimiter=';')
    df2 = pd.read_csv(file, delimiter=';')

    # Ensure no NaN values for comparison
    df1.fillna('')
    df2.fillna('')

    # Sort both DataFrames by all columns to ensure order independence
    df1_sorted = df1.sort_values(by="Route", ascending=True, inplace=False).reset_index(drop=True)
    df2_sorted = df2.sort_values(by="Route", ascending=True, inplace=False).reset_index(drop=True)

    # Find differences
    diff1 = df1_sorted[~df1_sorted.isin(df2_sorted.to_dict(orient='list')).all(axis=1)].copy()
    diff2 = df2_sorted[~df2_sorted.isin(df1_sorted.to_dict(orient='list')).all(axis=1)].copy()

    # Add a column indicating the source file
    diff1['Source'] = 'File1'
    diff2['Source'] = 'File2'

    # Combine differences
    combined_differences = pd.concat([diff1, diff2], ignore_index=True)

    # Compute fuzzy similarity for unmatched rows
    total_similarity = 0
    count = 0
    total_pairs = len(diff1) * len(diff2)
    logging.info(f"Fuzzy-matching {len(diff1)} removed row(s) against {len(diff2)} added row(s) - {total_pairs} comparisons...")
    progress_step = max(total_pairs // 10, 1)

    # Precompute each row's string form once instead of recomputing it on every pairing
    diff1_strs = [row.drop('Source').to_string(index=False) for _, row in diff1.iterrows()]
    diff2_strs = [row.drop('Source').to_string(index=False) for _, row in diff2.iterrows()]

    for s1 in diff1_strs:
        for s2 in diff2_strs:
            similarity = fuzz.ratio(s1, s2)
            total_similarity += similarity
            count += 1
            if count % progress_step == 0:
                logging.info(f"Fuzzy match progress: {count}/{total_pairs} ({count / total_pairs:.0%})")

    # Calculate overall similarity ratio
    overall_similarity = total_similarity / count if count > 0 else 100  # 100% if no unmatched rows
    # Save the differences to a CSV file
    combined_differences.to_csv('./Differences/differences.csv', index=False, sep=';')
    return (f"Overall Similarity Ratio: {overall_similarity:.2f}%"), diff1, diff2
        

