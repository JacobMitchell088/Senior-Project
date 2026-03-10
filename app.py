from fastapi import FastAPI
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
import os

import GBIF
from openai_species_context import enrich_gbif_results_with_openai_batch

app = FastAPI(
    title="Environmental Screening API",
    description="Environmental screening for endangered species near construction sites",
    version="1.0"
)

# Allow frontend requests during development / deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request schema
class ScanRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude of the construction site")
    lon: float = Field(..., ge=-180, le=180, description="Longitude of the construction site")
    radius_miles: float = Field(default=0, ge=0, le=100, description="Radius in miles")


@app.get("/")
def root():
    return {"message": "Environmental Screening API is running"}


@app.post("/scan")
def scan_site(req: ScanRequest):
    lat = req.lat
    lon = req.lon
    radius_miles = req.radius_miles

    # 1) Load precomputed Illinois endangered lookup
    name_to_key, key_to_name = GBIF.load_precomputed_taxon_keys("IllinoisTaxonLookup.csv")

    # 2) ONE GBIF call for all species keys in the area
    area_species = GBIF.gbif_species_counts_in_area(lat, lon, radius_miles)

    # 3) Intersect locally with Illinois endangered species keys
    hits = []
    for taxon_key, count in area_species:
        if taxon_key in key_to_name:
            name = key_to_name[taxon_key]
            hits.append((name, count, taxon_key))

    hits.sort(key=lambda x: x[1], reverse=True)

    # 4) Cap species count for OpenAI enrichment
    max_species = int(os.getenv("MAX_SPECIES_FOR_AI", GBIF.MAX_SPECIES))
    hits_for_ai = hits[:max_species]

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
            for nm, cnt, key in hits_for_ai
        ]
    }

    # 5) OpenAI enrichment
    enriched = enrich_gbif_results_with_openai_batch(gbif_result)

    return {
        "input": gbif_result["input"],
        "gbif_hits": [
            {
                "scientific_name": nm,
                "gbif_count": cnt,
                "taxon_key": key
            }
            for nm, cnt, key in hits
        ],
        "species_context": enriched["species_context"]
    }