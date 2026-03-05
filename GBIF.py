import requests

# Location (example: Chicago)
latitude = 41.8781
longitude = -87.6298
radius_km = 75  # ~25 miles

# Step 1: Query GBIF occurrence API
occurrence_url = "https://api.gbif.org/v1/occurrence/search"

params = {
    "decimalLatitude": latitude,
    "decimalLongitude": longitude,
    "distance": radius_km,
    "hasCoordinate": "true",
    "facet": "speciesKey",
    "facetMincount": 1,
    "limit": 0
}

response = requests.get(occurrence_url, params=params)
data = response.json()
print(data)  # Debug: Print the raw API response to understand its structure

species_counts = data["facets"][0]["counts"]

print("\nSpecies detected within 25 miles:\n")
print("Species Name | Occurrence Count")
print("-----------------------------------")

# Step 2: Resolve speciesKey → species name
for entry in species_counts[:20]:  # limit to top 20 species
    species_key = entry["name"]
    count = entry["count"]

    species_url = f"https://api.gbif.org/v1/species/{species_key}"
    species_response = requests.get(species_url)
    species_data = species_response.json()

    species_name = species_data.get("canonicalName", "Unknown")

    print(f"{species_name:<30} {count}")