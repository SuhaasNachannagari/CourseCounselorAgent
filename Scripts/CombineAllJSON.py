import json

combined_data = []

# Loop through cleanedgrades1.json to cleanedgrades10.json
for i in range(1, 11):
    filename = f"cleanedgrades{i}.json"
    with open(filename, "r") as f:
        data = json.load(f)
        combined_data.extend(data)  # Assuming each file contains a list of dicts

# Save to a single combined file
with open("all_cleanedgrades.json", "w") as f:
    json.dump(combined_data, f, indent=4)
