from fastapi import FastAPI
from pydantic import BaseModel
import os

# Import functions from GBIF module
import GBIF

from openai_species_context import enrich_gbif_results_with_openai_batch

app = FastAPI(
    title="Environmental Screening API",
    description="Environmental screening for endangered species near construction sites",
    version="1.0"
)

# Request schema
class ScanRequest(BaseModel):
    lat: float
    lon: float
    radius_miles: float


@app.get("/")
def root():
    return {"message": "Environmental Screening API is running"}


@app.post("/scan")
def scan_site(req: ScanRequest):

    lat = req.lat
    lon = req.lon
    radius_miles = req.radius_miles

    radius_km = GBIF.miles_to_km(radius_miles)
    geom = GBIF.bounding_box_polygon(lat, lon, radius_km)

    il_names = GBIF.load_il_scientific_names("IsEndangered.csv")

    # Map species name to taxon key
    name_to_key = {}
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(GBIF.gbif_match_to_taxonkey, nm): nm for nm in il_names}
        for fut in as_completed(futures):
            nm = futures[fut]
            try:
                key = fut.result()
                if key:
                    name_to_key[nm] = key
            except Exception:
                pass

    hits = []

    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {
            ex.submit(GBIF.gbif_count_occurrences, geom, key): (nm, key)
            for nm, key in name_to_key.items()
        }

        for fut in as_completed(futures):
            nm, key = futures[fut]
            try:
                cnt = fut.result()
                if cnt > 0:
                    hits.append((nm, cnt, key))
            except Exception:
                pass

    hits.sort(key=lambda x: x[1], reverse=True)

    # Cap species count (same behavior as GBIF.py)
    MAX_SPECIES = int(os.getenv("MAX_SPECIES_FOR_AI", 10))
    hits = hits[:MAX_SPECIES]

    gbif_result = {
        "input": {
            "lat": lat,
            "lon": lon,
            "radius_miles": radius_miles,
            "year_start": 2020,
            "year_end": 2025
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

    return {
        "gbif_hits": gbif_result["hits"],
        "species_context": enriched["species_context"]
    }