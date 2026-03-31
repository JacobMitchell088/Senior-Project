"""
openai_species_context.py

Generate short species-specific construction context for screening using the OpenAI Responses API.

Requirements
    conda activate GBIF_env

Environment
    OPENAI_API_KEY must be set in your environment.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from openai import OpenAI

DEFAULT_MODEL = "gpt-5.4"


def _build_batch_prompt(gbif_result: Dict[str, Any]) -> str:
    input_data = gbif_result.get("input", {})
    hits = gbif_result.get("hits", [])

    lat = input_data.get("lat")
    lon = input_data.get("lon")
    radius_miles = input_data.get("radius_miles")
    year_start = input_data.get("year_start")
    year_end = input_data.get("year_end")

    species_lines = []
    for hit in hits:
        scientific_name = hit.get("scientific_name", "Unknown")
        gbif_count = hit.get("gbif_count", "Unknown")
        taxon_key = hit.get("taxon_key", "Unknown")
        species_lines.append(
            f"- Scientific name: {scientific_name} | GBIF count: {gbif_count} | taxon key: {taxon_key}"
        )

    species_block = "\n".join(species_lines)

    return f"""
You are helping with an early-stage construction planning tool for Illinois.

A construction site has been screened for Illinois endangered species using GBIF occurrence data.

Construction site context:
- Latitude: {lat}
- Longitude: {lon}
- Radius screened: {radius_miles} miles
- GBIF year filter: {year_start if year_start is not None else "unknown"} to {year_end if year_end is not None else "present"}

Flagged species:
{species_block}

For EACH species, provide:
1. scientific_name
2. common_name (the widely-used English common name for this species)
3. tags: a compact list of 2–6 short keyword labels (1–3 words each) summarizing the most relevant concerns for this species — draw from seasonal sensitivities (e.g. "Nesting", "Breeding Season", "Migration", "Overwintering", "Spawning", "Dormancy") and disruptive activities (e.g. "Tree Clearing", "Ground Disturbance", "Vibration", "Noise", "Water Disturbance", "Night Lighting"). Only include tags that genuinely apply.
4. overview: 1–2 sentences of general background relevant to construction planning for this species
5. seasonal_concerns: a short paragraph on the most relevant seasonal sensitivities (breeding, nesting, migration, roosting, dormancy, spawning, etc.) and approximately when they occur
6. disruptive_activities: a short paragraph on which construction activities are most likely to cause disturbance (noise, tree clearing, grading, vibration, water disturbance, nighttime lighting, etc.)
7. recommendation: a cautious 1–2 sentence suggestion for when or how construction might be less disruptive, if reasonable — do not frame this as approval or a guarantee

Important rules:
- Do not invent legal requirements
- Do not say construction is approved or safe
- Do not sound absolute or definitive
- Keep the tone practical for a construction manager
- Mention uncertainty when appropriate

Return ONLY valid JSON in this exact format:
{{
  "species_context": [
    {{
      "scientific_name": "Species name here",
      "common_name": "Common name here",
      "tags": ["Tag One", "Tag Two"],
      "overview": "Brief general context here.",
      "seasonal_concerns": "Seasonal sensitivity paragraph here.",
      "disruptive_activities": "Disruptive activities paragraph here.",
      "recommendation": "Cautious timing suggestion here."
    }}
  ]
}}
""".strip()


def enrich_gbif_results_with_openai_batch(
    gbif_result: Dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    client: Optional[OpenAI] = None,
) -> Dict[str, Any]:
    if client is None:
        client = OpenAI()

    hits = gbif_result.get("hits", [])
    if not hits:
        return {
            "input": gbif_result.get("input", {}),
            "species_context": [],
            "disclaimer": (
                "These summaries are AI-generated planning aids based on species names and site context. "
                "They are not regulatory determinations and should be validated with qualified environmental professionals."
            ),
        }

    prompt = _build_batch_prompt(gbif_result)

    response = client.responses.create(
        model=model,
        input=prompt,
    )

    raw_text = response.output_text.strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {
            "species_context": [
                {
                    "scientific_name": "ParsingError",
                    "analysis": raw_text
                }
            ]
        }

    return {
        "input": gbif_result.get("input", {}),
        "species_context": parsed.get("species_context", []),
        "disclaimer": (
            "These summaries are AI-generated planning aids based on species names and site context. "
            "They are not regulatory determinations and should be validated with qualified environmental professionals."
        ),
    }