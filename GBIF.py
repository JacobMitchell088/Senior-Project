# GBIF.py

import csv
import math
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Stop early if your key isn't set in environment through .env or cli
import os
api_key = os.getenv("OPENAI_API_KEY")
if "OPENAI_API_KEY" not in os.environ:
    raise RuntimeError("OPENAI_API_KEY environment variable not set. Please rerun after setting your key.")


GBIF_OCC_SEARCH = "https://api.gbif.org/v1/occurrence/search"
MAX_SPECIES = int(os.getenv("MAX_SPECIES_FOR_AI", 3)) # Highest amount of species that can be sent to our openAI call

def miles_to_km(mi: float) -> float:
    return mi * 1.609344

# Bounding box over polygon for simplicity - Change to polygon later on for more specificity
def get_bounding_box(lat: float, lon: float, radius_miles: float):
    radius_km = miles_to_km(radius_miles)

    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)) + 1e-12)

    min_lat = lat - lat_delta
    max_lat = lat + lat_delta
    min_lon = lon - lon_delta
    max_lon = lon + lon_delta

    print(f"Bounding box = [min_lat: {min_lat}, max_lat: {max_lat}, min_lon: {min_lon}, max_lon: {max_lon}]")

    return min_lat, max_lat, min_lon, max_lon

def load_precomputed_taxon_keys(path: str) -> dict[str, int]:
    """
    Reads IllinoisTaxonLookup.csv and returns:

        {
            "Myotis sodalis": 2435099,
            "Pandion haliaetus": 2480506,
            ...
        }
    """

    name_to_key = {}
    key_to_name = {}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            name = (row.get("Scientific Name") or "").strip()
            key = (row.get("Taxon Key") or "").strip()

            if name and key:
                try:
                    name_to_key[name] = int(key)
                    key_to_name[int(key)] = name 
                except ValueError:
                    pass

    return name_to_key, key_to_name

def gbif_species_counts_in_area(lat: float, lon: float, radius_miles: float) -> list[tuple[int, int]]: # Do facet search to get ALL species keys in an area, then later cross section w/ precomputed list of IL endangered species keys
    min_lat, max_lat, min_lon, max_lon = get_bounding_box(lat, lon, radius_miles)
    
    params = {
        "decimalLatitude": f"{min_lat},{max_lat}",
        "decimalLongitude": f"{min_lon},{max_lon}",
        "hasCoordinate": "true",
        "year": "2025,2026",
        "facet": "speciesKey",
        "facetMincount": 1,
        "speciesKey.facetLimit": 1000,
        "limit": 0
    }

    j = requests.get(GBIF_OCC_SEARCH, params=params, timeout=45).json()

    counts = j.get("facets", [])[0].get("counts", [])
    return [(int(row["name"]), int(row["count"])) for row in counts if row.get("name")]

def main():
    # Example location
    # TODO:
    lat, lon = 38.617110, -90.207191
    radius_miles = 5

    #geom = bounding_box_polygon(lat, lon, radius_km)

    # 1) Load IL endangered species scientific names / taxon IDS (precomputed for speed)
    name_to_key, key_to_name = load_precomputed_taxon_keys("IllinoisTaxonLookup.csv")
    print(f"Loaded Illinois Taxon Keys: {len(name_to_key)} species")

    # 2) GBIF Query to get species counts in area - ONE CALL to get ALL species keys + counts in area (instead of iterating through each species and making separate calls)
    area_species = gbif_species_counts_in_area(lat, lon, radius_miles)
    print(f"GBIF species keys in area: {len(area_species)}")

    # 3) Cross reference GBIF species keys with IL endangered species keys to get final hits with counts and names (intersect locally)
    hits = []
    
    for taxon_key, count in area_species:
        if taxon_key in key_to_name:
            name = key_to_name[taxon_key]
            hits.append((name, count, taxon_key))

    hits.sort(key=lambda x: x[1], reverse=True)

    print(f"\nIL endangered species with GBIF occurrences in ~{radius_miles} miles:\n")
    if not hits:
        print("No matches found.")
        return

    print(f"{'Scientific Name':35} {'GBIF Count':>10} {'taxonKey':>10}")
    print("-" * 60)
    for nm, cnt, key in hits:
        print(f"{nm[:35]:35} {cnt:10d} {key:10d}")


    hits = hits[:MAX_SPECIES] # Cap for at most 10 of our species to be sent for additional context for openai

    # openAI --- additional context calls
    from openai_species_context import enrich_gbif_results_with_openai_batch

    # Convert results into the structure expected by the OpenAI module
    gbif_result = {
        "input": {
            "lat": lat,
            "lon": lon,
            "radius_miles": radius_miles,
            "year_start": 2025,
            "year_end": 2026
        },
        "hits": [
            {
                "scientific_name": nm,
                "gbif_count": cnt,
                "taxon_key": key
            }
            for nm, cnt, key in hits
        ]
    }

    enriched = enrich_gbif_results_with_openai_batch(gbif_result)

    print("\nAI Species Context:\n")

    for item in enriched["species_context"]:
        print(item["scientific_name"])
        print(item["analysis"])
        print()

if __name__ == "__main__":
    main()