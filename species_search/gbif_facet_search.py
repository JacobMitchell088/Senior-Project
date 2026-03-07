import requests
from datetime import datetime

GBIF_OCCURRENCE_URL = "https://api.gbif.org/v1/occurrence/search"


def get_unique_species_in_radius(lat, lon, radius_km, years_back=3):
    """
    Returns a list of unique species observed within a radius of a coordinate.
    Uses GBIF faceting so only one API call is needed regardless of occurrence count.

    Args:
        lat (float): Latitude of center point
        lon (float): Longitude of center point
        radius_km (int/float): Search radius in kilometers
        years_back (int): How many years back to search (default 3)

    Returns:
        list of dictionaries with speciesKey and count
    """

    # GBIF geoDistance expects meters
    radius_m = radius_km * 1000

    # Calculate year range
    current_year = datetime.now().year
    start_year = current_year - years_back

    # Parameters specifically for GBIF's occurrence/search API call
    params = {
        'geoDistance': f'{lat},{lon},{radius_m}',   # radius around coordinate (km converted to meters)
        'hasCoordinate': 'true',
        'hasGeospatialIssue': 'false',
        'occurrenceStatus': 'PRESENT',
        'basisOfRecord': 'HUMAN_OBSERVATION',
        'year': f'{start_year},{current_year}',
        'facet': 'speciesKey',                      # collapse into unique species
        'facetLimit': 1000000,                      # return up to 1,000,000 unique species (should never be reached)
        'limit': 0                                  # don't return individual occurrences
    }

    print(f"Searching within {radius_km}km of ({lat}, {lon}) from {start_year} to {current_year}...")

    # Building the api call
    response = requests.get(GBIF_OCCURRENCE_URL, params=params)

    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}")
        return []

    # Extract results
    data = response.json()
    facets = data.get('facets', [])

    if not facets:
        print("No facet results returned.")
        return []

    # Find the speciesKey facet
    species_facet = next((f for f in facets if f['field'] == 'SPECIES_KEY'), None)

    if not species_facet:
        print("No species facet found in response.")
        return []

    # Stores the speciesKey as 'key' and occurrenceCount as 'value' in species_list dictionary
    species_list = []
    for entry in species_facet.get('counts', []):
        species_list.append({
            'speciesKey': int(entry['name']),
            'occurrenceCount': entry['count']
        })

    returned_species = len(species_list)

    print(f"Returned {returned_species} unique species (facetLimit: {params['facetLimit']})")

    # Check if we hit the facetLimit and may be missing species
    if returned_species >= params['facetLimit']:
        print(f"WARNING: Hit the facetLimit of {params['facetLimit']}.")
        print(f"There may be additional species in this area that were not returned.")
        print(f"Consider reducing your search radius or increasing facetLimit.")
    else:
        print(f"facetLimit not hit — all unique species in area were returned.")

    return species_list, returned_species, params['facetLimit']

# This prints all speciesKeys with occurrenceCounts in the radius. Not needed for finding threatened species
def display_results(species_list, returned_count, facet_limit):
    if not species_list:
        print("No species found.")
        return

    print(f"\n{'Species Key':<15} {'Occurrence Count':<20}")
    print("-" * 35)
    for s in species_list:
        print(f"{s['speciesKey']:<15} {s['occurrenceCount']:<20}")

    # Summary at the bottom
    print("-" * 35)
    print(f"Total returned: {returned_count} species")
    if returned_count >= facet_limit:
        print(f"   WARNING: Results were capped at facetLimit ({facet_limit}).")
        print(f"   Rare species may be missing. Try a smaller radius.")
    else:
        print(f"   All species in area returned (did not hit facetLimit).")


# Don't need to change values here except when testing an altered function
if __name__ == "__main__":
    # Example: 10km radius around Edwardsville, Illinois
    LATITUDE   = 38.793864
    LONGITUDE  = -89.999411
    RADIUS_KM = 2

    species_list, returned_count, facet_limit = get_unique_species_in_radius(
        LATITUDE, LONGITUDE, RADIUS_KM, years_back=3
    )
    display_results(species_list, returned_count, facet_limit)



# ------- Example Output for first three species ------- #
'''
Searching within 2km of (38.8114, -89.9534) from 2023 to 2026...
Returned 333 unique species (facetLimit: 200000)
facetLimit not hit — all unique species in area were returned.

Species Key     Occurrence Count    
-----------------------------------
2490384         621
2487887         526
2493801         519
'''
