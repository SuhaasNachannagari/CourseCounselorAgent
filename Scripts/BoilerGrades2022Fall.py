import pandas as pd
import json
import numpy as np


#Cleaning for 2016 ti 2021
file_path = "../RawBoilerGrades/rawgrades2022fall.csv"

df = pd.read_csv(file_path, skiprows=7, header=1)

def smart_forward_fill(series):
    filled = []
    last_value = None
    for val in series:
        if pd.notna(val):
            last_value = val
            filled.append(val)
        else:
            filled.append(last_value)
    return pd.Series(filled, index=series.index)



# Drop unwanted columns
df.drop(columns=["Section", "CRN", "Academic Period", "% of Total.28", "% of Total.25"], inplace=True)
df = df.loc[:, ~df.columns.str.contains("student", case=False)]

# Rename column
df.rename(columns={"Academic Period Desc": "Academic Period"}, inplace=True)
grade_map = {
    "A": "a_pct",
    "A-": "a_minus_pct",
    "A+": "a_plus_pct",
    "AU": "audit_pct",            # Audit
    "B": "b_pct",
    "B-": "b_minus_pct",
    "B+": "b_plus_pct",
    "C": "c_pct",
    "C-": "c_minus_pct",
    "C+": "c_plus_pct",
    "D": "d_pct",
    "D-": "d_minus_pct",
    "D+": "d_plus_pct",
    "E": "e_pct",                 # Sometimes equivalent to F
    "F": "f_pct",
    "I": "incomplete_pct",
    "N": "not_passed_pct",        # Used for pass/no-pass
    "NS": "no_show_pct",          # Did not show up
    "P": "pass_pct",
    "PI": "permanent_incomplete_pct",
    "S": "satisfactory_pct",
    "SI": "satisfactory_incomplete_pct",
    "U": "unsatisfactory_pct",
    "W": "withdrawn_pct",
    "WF": "withdrawn_failing_pct",
    "WN": "withdrawn_never_attended_pct",
    "WU": "withdrawn_unknown_pct"
}



grade_labels = [
    "A", "A-", "A+", "AU", "B", "B-", "B+", "C", "C-", "C+", "D", "D-", "D+",
    "E", "F", "I", "N", "NS", "P", "PI", "S", "SI", "U", "W", "WF", "WN", "WU"
]

start_idx = 6

for i, grade in enumerate(grade_labels):
    df.columns.values[start_idx + i] = grade_map.get(grade, grade)

columns_to_fill = ["Subject", "Subject Desc", "Course Number", "Title", "Academic Period"]

for col in columns_to_fill:
    df[col] = smart_forward_fill(df[col])

pd.set_option("display.max_columns", None)


percentage_columns = [col for col in df.columns if '_pct' in col]

print("\n--- Cleaning and Converting ---")
for col in percentage_columns:
    cleaned_series = df[col].astype(str).str.replace('%', '').str.replace('<', '')
    df[col] = pd.to_numeric(cleaned_series, errors='coerce')




gpa_map = {
    'a_plus_pct': 4.0, 'a_pct': 4.0, 'a_minus_pct': 3.7,
    'b_plus_pct': 3.3, 'b_pct': 3.0, 'b_minus_pct': 2.7,
    'c_plus_pct': 2.3, 'c_pct': 2.0, 'c_minus_pct': 1.7,
    'd_plus_pct': 1.3, 'd_pct': 1.0, 'd_minus_pct': 0.7,
    'f_pct': 0.0, 'e_pct': 0.0, 'withdrawn_failing_pct': 0.0,
}

grade_cols = [col for col in df.columns if col in gpa_map]
df_grades = df[grade_cols].copy()

sum_of_reported_pct = df_grades.sum(axis=1)

sum_of_reported_pct.replace(0, np.nan, inplace=True)

normalized_grades = df_grades.div(sum_of_reported_pct, axis=0)

normalized_grades.fillna(0, inplace=True)
gpa_estimate = (normalized_grades * pd.Series(gpa_map)).sum(axis=1)

df['gpa_estimate_normalized'] = gpa_estimate

print(df[['Subject', 'Course Number', 'Instructor', 'gpa_estimate_normalized']].round(2))


json_output = df.to_dict(orient="records")
print(json_output[:2])

final_display_cols = grade_cols + ['gpa_estimate_normalized']
json_output = df.to_json(orient="records", indent=4)

file_path = 'cleanedgrades5.json'

df.to_json(file_path, orient='records', indent=4, date_format='iso')

#Clean up Fall 2021


print(df.columns)

