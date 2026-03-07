import sqlite3
import pandas as pd
import time


DB_PATH = "database/threatened_species.db"
BACKBONE_PATH = "database/Taxon.tsv"       # path to your GBIF backbone file
BATCH_SIZE = 500                   # how many species to process before saving progress


# LOAD GBIF BACKBONE INTO MEMORY
def load_backbone():
    """
    Loads the GBIF Taxon.tsv file into a pandas dataframe.
    Filters to only accepted species to reduce memory usage.
    Builds a dictionary for fast name lookups.
    """
    print("Loading GBIF backbone file (this may take a moment)...")

    # Only load the columns we need to keep memory usage down
    cols = ['taxonID', 'canonicalName', 'taxonRank', 'taxonomicStatus', 'class', 'kingdom']

    df = pd.read_csv(
        BACKBONE_PATH,
        sep='\t',
        usecols=cols,
        dtype=str,
        low_memory=False,
        on_bad_lines='skip'     # skip any malformed rows
    )

    # Filter to accepted species only
    df = df[
        (df['taxonRank'].str.upper() == 'SPECIES') &
        (df['taxonomicStatus'].str.lower() == 'accepted')
    ]

    print(f"Backbone loaded: {len(df)} accepted species found")

    # Build a dictionary for fast lookup: canonicalName -> taxonID
    # This turns every lookup from a slow scan into an instant dictionary lookup
    backbone_dict = {}
    for _, row in df.iterrows():
        name = str(row['canonicalName']).strip()
        if name and name != 'nan':
            backbone_dict[name] = {
                'taxonID': row['taxonID'],
                'class':   row.get('class', ''),
                'kingdom': row.get('kingdom', '')
            }

    print(f"Lookup dictionary built with {len(backbone_dict)} entries")

    # Build a second unfiltered dictionary as a fallback for NONE matches
    # This catches cases where a species exists in GBIF but got filtered out
    # due to rank or status differences (e.g. only exists as subspecies entries)
    print("Building fallback dictionary from full backbone...")

    df_full = pd.read_csv(
        BACKBONE_PATH,
        sep='\t',
        usecols=cols,
        dtype=str,
        low_memory=False,
        on_bad_lines='skip'
    )

    fallback_dict = {}
    for _, row in df_full.iterrows():
        name = str(row['canonicalName']).strip()
        # Only add if not already in main dict to avoid overwriting clean matches
        if name and name != 'nan' and name not in backbone_dict:
            fallback_dict[name] = {
                'taxonID': row['taxonID'],
                'class':   row.get('class', ''),
                'kingdom': row.get('kingdom', '')
            }

    print(f"Fallback dictionary built with {len(fallback_dict)} additional entries")
    return backbone_dict, fallback_dict


# GET UNMATCHED SPECIES FROM DATABASE
def get_unmatched_species():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT iucn_id, scientific_name 
        FROM threatened_species 
        WHERE gbif_species_key IS NULL OR match_type = 'NONE'
        ORDER BY iucn_id
    ''')

    rows = cursor.fetchall()
    conn.close()

    print(f"Found {len(rows)} unmatched or NONE species to process")
    return rows


# MATCH A SINGLE SPECIES NAME
def match_species(scientific_name, backbone_dict, fallback_dict):
    """
    Tries to match a scientific name against the GBIF backbone dictionary.
    Returns (taxonID, match_type).

    Match types:
    - EXACT: perfect match on accepted species level entry
    - FUZZY: matched after cleaning/simplifying the name or via fallback
    - NONE: no match found anywhere in backbone
    """
    name = scientific_name.strip()

    # Try exact match against accepted species dict
    if name in backbone_dict:
        return backbone_dict[name]['taxonID'], 'EXACT'

    # Try trimming to first two words (genus + species)
    # handles cases like "Panthera leo ssp. something" vs "Panthera leo"
    parts = name.split()
    if len(parts) > 2:
        short_name = f"{parts[0]} {parts[1]}"
        if short_name in backbone_dict:
            return backbone_dict[short_name]['taxonID'], 'FUZZY'

    # Try case insensitive match against accepted species dict
    name_lower = name.lower()
    for key, value in backbone_dict.items():
        if key.lower() == name_lower:
            return value['taxonID'], 'FUZZY'

    # Try exact match against full unfiltered backbone
    # catches species that exist in GBIF but weren't in accepted species filter
    if name in fallback_dict:
        return fallback_dict[name]['taxonID'], 'FUZZY'

    # Try trimming to two words against fallback dict
    if len(parts) > 2:
        short_name = f"{parts[0]} {parts[1]}"
        if short_name in fallback_dict:
            return fallback_dict[short_name]['taxonID'], 'FUZZY'

    return None, 'NONE'


# UPDATE DATABASE WITH MATCHES
def update_species_batch(matches):
    """
    Updates a batch of species rows with their GBIF keys.
    matches is a list of (gbif_species_key, match_type, iucn_id) tuples.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.executemany('''
        UPDATE threatened_species
        SET gbif_species_key = ?, match_type = ?
        WHERE iucn_id = ?
    ''', matches)

    conn.commit()
    conn.close()


def print_summary():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM threatened_species")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT match_type, COUNT(*) FROM threatened_species GROUP BY match_type")
    rows = cursor.fetchall()

    print(f"\nMatching Summary ({total} total species):")
    for row in rows:
        match_type = row[0] if row[0] else 'UNPROCESSED'
        print(f"  {match_type}: {row[1]}")

    conn.close()


# MAIN
if __name__ == "__main__":

    # Load backbone into memory
    backbone_dict, fallback_dict = load_backbone()

    # Get all unmatched species from database
    unmatched = get_unmatched_species()

    if not unmatched:
        print("All species already matched. Nothing to do.")
        print_summary()
        exit()

    # Match species and save in batches
    batch = []
    exact = 0
    fuzzy = 0
    none  = 0

    for i, (iucn_id, scientific_name) in enumerate(unmatched):

        taxon_id, match_type = match_species(scientific_name, backbone_dict, fallback_dict)

        batch.append((taxon_id, match_type, iucn_id))

        if match_type == 'EXACT': exact += 1
        if match_type == 'FUZZY': fuzzy += 1
        if match_type == 'NONE':  none  += 1

        # Save progress every BATCH_SIZE species
        if len(batch) >= BATCH_SIZE:
            update_species_batch(batch)
            batch = []
            print(f"  Progress: {i + 1}/{len(unmatched)} processed "
                  f"(EXACT: {exact}, FUZZY: {fuzzy}, NONE: {none})")

    # Save any remaining species in the last partial batch
    if batch:
        update_species_batch(batch)
        print(f"  Progress: {len(unmatched)}/{len(unmatched)} processed "
              f"(EXACT: {exact}, FUZZY: {fuzzy}, NONE: {none})")

    # Final summary
    print_summary()
    print("\nDone! Your database now has GBIF species keys paired with IUCN threat status.")
