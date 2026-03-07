# Species Search

This folder contains two files that work together to find threatened species observed near a given location. `gbif_facet_search.py` handles communication with the GBIF API, and `find_threatened_species.py` uses those results to identify which species are threatened by cross-referencing a local database.

---

## Requirements

Set up the environment using the provided `environment.yml` file:

```bash
conda env create -f environment.yml
conda activate search_env
```

The database file `database/threatened_species.db` must exist before running either file. See the `database/` folder and its README for instructions on building it.

---

## gbif_facet_search.py

### What It Does

Sends a single request to the GBIF occurrence API for a given location and radius. Instead of returning every individual sighting, it uses GBIF's faceting feature to collapse results into a list of unique species and how many times each was observed. This avoids the performance problem of paginating through tens of thousands of individual occurrence records.

### How to Run

Update the search parameters at the bottom of the file:

```python
LATITUDE   = 38.8114
LONGITUDE  = -89.9534
RADIUS_KM  = 25
```

Then run:

```bash
python gbif_facet_search.py
```

### Example Output

```
Searching within 2km of (38.793864, -89.999411) from 2023 to 2026...
Returned 803 unique species (facetLimit: 1000000)
facetLimit not hit — all unique species in area were returned.

Species Key     Occurrence Count    
-----------------------------------
2490384         148                 
2487887         132                 
2482593         118                 
2478106         113                 
2493801         108                 
2482507         106                 
.
.
.
9651791         1                   
9776414         1                   
9778438         1                   
9998920         1                   
-----------------------------------
Total returned: 803 species
   All species in area returned (did not hit facetLimit).
```

### Notes

- `RADIUS_KM` can be any value but larger radii return more species and take longer to cross-reference. A radius of 5–50km is recommended for typical use.
- Results are limited to human observations (`basisOfRecord: HUMAN_OBSERVATION`) from the last 3 years by default.
- If the number of returned species equals the `facetLimit`, a warning is shown indicating some species may have been cut off. This is unlikely with the current limit of 1,000,000.

---

## find_threatened_species.py

### What It Does

The main search file. Calls `gbif_facet_search.py` to get all unique species observed in an area, then looks up which of those species are in the threatened species database. Results are grouped by threat category and displayed with occurrence counts.

### How to Run

Update the search parameters at the bottom of the file:

```python
LATITUDE   = 38.8114
LONGITUDE  = -89.9534
RADIUS_KM  = 25
YEARS_BACK = 3
```

Then run:

```bash
python find_threatened_species.py
```

### Example Output

```
Searching within 5km of (38.793864, -89.999411) from 2023 to 2026...
Returned 1247 unique species (facetLimit: 1000000)
facetLimit not hit — all unique species in area were returned.

Cross referencing 1247 species against threatened species database...

============================================================
THREATENED SPECIES FOUND IN AREA
============================================================
Total unique species in area:    1247
Threatened species found:        12
============================================================

--- Endangered (EN) --- 1 species
  Pandion haliaetus                             8 sightings

--- Vulnerable (VU) --- 11 species
  Anas acuta                                    2 sightings
  Bombus pensylvanicus                          5 sightings
  Chaetura pelagica                             210 sightings
  Circus cyaneus                                2 sightings
  Euphagus carolinus                            8 sightings
  Falco columbarius                             1 sightings
  Gymnocladus dioicus                           4 sightings
  Hydrastis canadensis                          1 sightings
  Rhodotus palmatus                             1 sightings
  Terrapene carolina                            1 sightings
  Tringa flavipes                               1 sightings

============================================================
NOTE: Results are based on available GBIF observation data
and may not reflect all species present in the area.
============================================================

```

### Notes

- Results are grouped by threat status: Critically Endangered (CR), Endangered (EN), and Vulnerable (VU).
- Each result includes the scientific name and number of times that species was observed in the area.
- Species with a GBIF match type of NONE in the database will not appear in results even if they are threatened. See the database README for more details on match types.

---

## Disclaimer

Results are based on observation data submitted to GBIF and may not reflect all species present in an area. Threatened species data is sourced from the IUCN Red List. Some species may be matched at the species level rather than subspecies level due to naming differences between IUCN and GBIF. This tool is intended for educational and informational purposes only and should not be used as the sole basis for commercial or regulatory decisions.
