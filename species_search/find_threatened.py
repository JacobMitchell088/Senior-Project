import sqlite3
import sys
import os

# Import our facet search function from the other file
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from gbif_facet_search import get_unique_species_in_radius


DB_PATH = "database/threatened_species.db"

# Threat status labels for display
THREAT_LABELS = {
    'CR': 'Critically Endangered',
    'EN': 'Endangered',
    'VU': 'Vulnerable'
}

# CROSS REFERENCE KEYS WITH DATABASE
def find_threatened_in_area(species_keys):
    """
    Takes a list of GBIF species keys returned from the facet search
    and finds which ones are in our threatened species database.

    Uses a single SQL IN query so it runs in milliseconds regardless
    of how many keys are passed in.

    Returns a list of dicts with species info + occurrence count.
    """
    if not species_keys:
        return []

    # Build a lookup dictionary of speciesKey -> occurrenceCount from facet results, so we can attach occurrence count to each matched species
    key_to_count = {s['speciesKey']: s['occurrenceCount'] for s in species_keys}

    # Extract just the keys for the SQL IN clause
    keys = list(key_to_count.keys())

    # Build placeholders for SQL query (one '?' per key)
    placeholders = ','.join(['?' for _ in keys])

    # SQL Query
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(f'''
        SELECT iucn_id, scientific_name, threat_status, gbif_species_key
        FROM threatened_species
        WHERE gbif_species_key IN ({placeholders})
        ORDER BY threat_status, scientific_name
    ''', keys)

    rows = cursor.fetchall()
    conn.close()

    # Build result list combining database info with occurrence count
    results = []
    for row in rows:
        iucn_id, scientific_name, threat_status, gbif_species_key = row
        results.append({
            'iucn_id':         iucn_id,
            'scientific_name': scientific_name,
            'threat_status':   threat_status,
            'threat_label':    THREAT_LABELS.get(threat_status, threat_status),
            'gbif_species_key': gbif_species_key,
            'occurrence_count': key_to_count.get(gbif_species_key, 0)
        })

    return results


def display_results(results, total_species_in_area):
    if not results:
        print("No threatened species found in this area.")
        return

    print(f"\n{'='*60}")
    print(f"THREATENED SPECIES FOUND IN AREA")
    print(f"{'='*60}")
    print(f"Total unique species in area:    {total_species_in_area}")
    print(f"Threatened species found:        {len(results)}")
    print(f"{'='*60}\n")

    # Group by threat status for clean display
    for code in ['CR', 'EN', 'VU']:
        group = [r for r in results if r['threat_status'] == code]
        if not group:
            continue

        print(f"--- {THREAT_LABELS[code]} ({code}) --- {len(group)} species")
        for r in group:
            print(f"  {r['scientific_name']:<45} {r['occurrence_count']} sightings")
        print()

    print(f"{'='*60}")
    print("NOTE: Results are based on available GBIF observation data")
    print("and may not reflect all species present in the area.")
    print(f"{'='*60}\n")


# MAIN
if __name__ == "__main__":

    # Search parameters (will be entered by users)
    LATITUDE   = 38.793864
    LONGITUDE  = -89.999411
    RADIUS_KM  = 5
    YEARS_BACK = 3

    # Get unique species in area from GBIF facet search
    species_list, returned_count, facet_limit = get_unique_species_in_radius(
        LATITUDE, LONGITUDE, RADIUS_KM, years_back=YEARS_BACK
    )

    if not species_list:
        print("No species returned from GBIF search.")
        exit()

    # Cross reference with threatened species database
    print(f"\nCross referencing {returned_count} species against threatened species database...")
    threatened = find_threatened_in_area(species_list)

    # Display results
    display_results(threatened, returned_count)
