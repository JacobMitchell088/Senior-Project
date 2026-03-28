"""
tests/test_openai_species_context.py

Unit tests for openai_species_context.py covering:
  - _build_batch_prompt()  — pure string-building function
  - enrich_gbif_results_with_openai_batch() — OpenAI call, JSON parsing, fallback

No patching is needed for the enrichment function because it accepts an
optional `client` parameter — we pass a MagicMock directly.
"""

import json
from unittest.mock import MagicMock

import pytest

from openai_species_context import (
    DEFAULT_MODEL,
    _build_batch_prompt,
    enrich_gbif_results_with_openai_batch,
)


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_INPUT = {
    "lat": 41.8781,
    "lon": -87.6298,
    "radius_miles": 5.0,
    "year_start": 2025,
    "year_end": 2026,
}

_HIT_SODALIS = {
    "scientific_name": "Myotis sodalis",
    "gbif_count": 42,
    "taxon_key": 2435099,
}

_HIT_PANDION = {
    "scientific_name": "Pandion haliaetus",
    "gbif_count": 17,
    "taxon_key": 2480506,
}

_ONE_SPECIES = {"input": _INPUT, "hits": [_HIT_SODALIS]}
_TWO_SPECIES = {"input": _INPUT, "hits": [_HIT_SODALIS, _HIT_PANDION]}
_NO_SPECIES  = {"input": _INPUT, "hits": []}

_VALID_OPENAI_JSON = json.dumps({
    "species_context": [
        {"scientific_name": "Myotis sodalis", "analysis": "Roosts in caves during winter."}
    ]
})


def _make_client(output_text: str) -> MagicMock:
    """Build a minimal mock OpenAI client whose responses.create() returns output_text."""
    mock_response = MagicMock()
    mock_response.output_text = output_text

    mock_client = MagicMock()
    mock_client.responses.create.return_value = mock_response
    return mock_client


# ---------------------------------------------------------------------------
# 1. _build_batch_prompt() — pure function
# ---------------------------------------------------------------------------

class TestBuildBatchPrompt:

    def test_returns_nonempty_string(self):
        prompt = _build_batch_prompt(_ONE_SPECIES)
        assert isinstance(prompt, str) and len(prompt) > 0

    # -- Site context embedded in prompt --

    def test_contains_latitude(self):
        prompt = _build_batch_prompt(_ONE_SPECIES)
        assert str(_INPUT["lat"]) in prompt

    def test_contains_longitude(self):
        prompt = _build_batch_prompt(_ONE_SPECIES)
        assert str(_INPUT["lon"]) in prompt

    def test_contains_radius(self):
        prompt = _build_batch_prompt(_ONE_SPECIES)
        assert str(_INPUT["radius_miles"]) in prompt

    def test_contains_year_start(self):
        prompt = _build_batch_prompt(_ONE_SPECIES)
        assert str(_INPUT["year_start"]) in prompt

    def test_contains_year_end(self):
        prompt = _build_batch_prompt(_ONE_SPECIES)
        assert str(_INPUT["year_end"]) in prompt

    def test_handles_none_year_start(self):
        data = {"input": {**_INPUT, "year_start": None}, "hits": [_HIT_SODALIS]}
        prompt = _build_batch_prompt(data)
        assert "unknown" in prompt.lower()

    def test_handles_none_year_end(self):
        data = {"input": {**_INPUT, "year_end": None}, "hits": [_HIT_SODALIS]}
        prompt = _build_batch_prompt(data)
        assert "present" in prompt.lower()

    # -- Species block --

    def test_contains_scientific_name(self):
        prompt = _build_batch_prompt(_ONE_SPECIES)
        assert "Myotis sodalis" in prompt

    def test_contains_gbif_count(self):
        prompt = _build_batch_prompt(_ONE_SPECIES)
        assert str(_HIT_SODALIS["gbif_count"]) in prompt

    def test_contains_taxon_key(self):
        prompt = _build_batch_prompt(_ONE_SPECIES)
        assert str(_HIT_SODALIS["taxon_key"]) in prompt

    def test_all_species_present_for_multiple_hits(self):
        prompt = _build_batch_prompt(_TWO_SPECIES)
        assert "Myotis sodalis" in prompt
        assert "Pandion haliaetus" in prompt

    def test_empty_hits_produces_empty_species_block(self):
        prompt = _build_batch_prompt(_NO_SPECIES)
        assert "Myotis sodalis" not in prompt

    # -- Output format instruction --

    def test_prompt_requests_json_output(self):
        """Model must be instructed to return JSON so the parser can handle it."""
        prompt = _build_batch_prompt(_ONE_SPECIES)
        assert "json" in prompt.lower()

    def test_prompt_requests_species_context_key(self):
        """The exact JSON key the parser expects must appear in the prompt."""
        prompt = _build_batch_prompt(_ONE_SPECIES)
        assert "species_context" in prompt


# ---------------------------------------------------------------------------
# 2. enrich_gbif_results_with_openai_batch()
# ---------------------------------------------------------------------------

class TestEnrichGbifResults:

    # -- Early-return path: no hits --

    def test_empty_hits_skips_api_call(self):
        mock_client = _make_client(_VALID_OPENAI_JSON)
        enrich_gbif_results_with_openai_batch(_NO_SPECIES, client=mock_client)
        mock_client.responses.create.assert_not_called()

    def test_empty_hits_returns_empty_species_context(self):
        result = enrich_gbif_results_with_openai_batch(
            _NO_SPECIES, client=_make_client(_VALID_OPENAI_JSON)
        )
        assert result["species_context"] == []

    def test_empty_hits_preserves_input(self):
        result = enrich_gbif_results_with_openai_batch(
            _NO_SPECIES, client=_make_client(_VALID_OPENAI_JSON)
        )
        assert result["input"] == _INPUT

    def test_empty_hits_still_returns_disclaimer(self):
        result = enrich_gbif_results_with_openai_batch(
            _NO_SPECIES, client=_make_client(_VALID_OPENAI_JSON)
        )
        assert "disclaimer" in result
        assert len(result["disclaimer"]) > 0

    # -- Happy path: valid JSON from API --

    def test_valid_response_parsed_correctly(self):
        result = enrich_gbif_results_with_openai_batch(
            _ONE_SPECIES, client=_make_client(_VALID_OPENAI_JSON)
        )
        assert len(result["species_context"]) == 1
        assert result["species_context"][0]["scientific_name"] == "Myotis sodalis"

    def test_valid_response_preserves_analysis_text(self):
        result = enrich_gbif_results_with_openai_batch(
            _ONE_SPECIES, client=_make_client(_VALID_OPENAI_JSON)
        )
        assert result["species_context"][0]["analysis"] == "Roosts in caves during winter."

    def test_valid_response_preserves_input(self):
        result = enrich_gbif_results_with_openai_batch(
            _ONE_SPECIES, client=_make_client(_VALID_OPENAI_JSON)
        )
        assert result["input"] == _INPUT

    def test_disclaimer_always_present_on_success(self):
        result = enrich_gbif_results_with_openai_batch(
            _ONE_SPECIES, client=_make_client(_VALID_OPENAI_JSON)
        )
        assert "disclaimer" in result
        assert len(result["disclaimer"]) > 0

    def test_api_called_exactly_once(self):
        mock_client = _make_client(_VALID_OPENAI_JSON)
        enrich_gbif_results_with_openai_batch(_ONE_SPECIES, client=mock_client)
        mock_client.responses.create.assert_called_once()

    def test_default_model_passed_to_api(self):
        mock_client = _make_client(_VALID_OPENAI_JSON)
        enrich_gbif_results_with_openai_batch(_ONE_SPECIES, client=mock_client)
        call_kwargs = mock_client.responses.create.call_args[1]
        assert call_kwargs["model"] == DEFAULT_MODEL

    def test_custom_model_passed_to_api(self):
        mock_client = _make_client(_VALID_OPENAI_JSON)
        enrich_gbif_results_with_openai_batch(
            _ONE_SPECIES, model="gpt-4o", client=mock_client
        )
        call_kwargs = mock_client.responses.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"

    def test_prompt_passed_as_input_to_api(self):
        """The API call must receive a non-empty prompt string."""
        mock_client = _make_client(_VALID_OPENAI_JSON)
        enrich_gbif_results_with_openai_batch(_ONE_SPECIES, client=mock_client)
        call_kwargs = mock_client.responses.create.call_args[1]
        assert isinstance(call_kwargs["input"], str)
        assert len(call_kwargs["input"]) > 0

    # -- Fallback path: invalid JSON from API --

    def test_invalid_json_does_not_raise(self):
        result = enrich_gbif_results_with_openai_batch(
            _ONE_SPECIES, client=_make_client("This is not JSON at all.")
        )
        assert "species_context" in result

    def test_invalid_json_fallback_scientific_name_is_parsing_error(self):
        result = enrich_gbif_results_with_openai_batch(
            _ONE_SPECIES, client=_make_client("This is not JSON at all.")
        )
        assert result["species_context"][0]["scientific_name"] == "ParsingError"

    def test_invalid_json_fallback_stores_raw_text_as_analysis(self):
        raw = "This is not JSON at all."
        result = enrich_gbif_results_with_openai_batch(
            _ONE_SPECIES, client=_make_client(raw)
        )
        assert result["species_context"][0]["analysis"] == raw

    def test_invalid_json_still_returns_disclaimer(self):
        result = enrich_gbif_results_with_openai_batch(
            _ONE_SPECIES, client=_make_client("bad json")
        )
        assert "disclaimer" in result

    # -- Edge case: valid JSON but missing species_context key --

    def test_missing_species_context_key_returns_empty_list(self):
        no_key_json = json.dumps({"something_else": []})
        result = enrich_gbif_results_with_openai_batch(
            _ONE_SPECIES, client=_make_client(no_key_json)
        )
        assert result["species_context"] == []

    # -- Edge case: response JSON with leading/trailing whitespace --

    def test_whitespace_around_json_handled(self):
        padded = f"  \n{_VALID_OPENAI_JSON}\n  "
        result = enrich_gbif_results_with_openai_batch(
            _ONE_SPECIES, client=_make_client(padded)
        )
        assert len(result["species_context"]) == 1
