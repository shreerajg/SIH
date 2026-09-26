"""Product understanding and the multi-round AI interview.

The behaviour worth protecting: the platform asks rather than assumes, the
questions are category-aware rather than generic, and a language model can
enrich the profile but never override what the user actually wrote.
"""
from __future__ import annotations

import json

import pytest

from app.services.product_interview import (
    MAX_QUESTIONS,
    PRODUCT_FAMILY_FIELD,
    ProductInterviewService,
)
from app.services.product_understanding import (
    ALLOWED_ATTRIBUTE_KEYS,
    ProductUnderstandingService,
    normalise_answer,
)
from app.services.taxonomy import field_specs_for, max_priority_for


# ---------------------------------------------------------------------------
# Deterministic extraction (the always-available path)
# ---------------------------------------------------------------------------

def test_deterministic_extraction_reads_quantities_from_the_sentence():
    profile = ProductUnderstandingService().analyze(
        "We manufacture a 15 litre domestic electric storage water heater at 230 V, 2000 W."
    )
    attributes = profile["attributes"]
    assert profile["category"] == "water-heater"
    assert attributes["capacity_litres"] == 15.0
    assert attributes["voltage_v"] == 230.0
    assert attributes["power_w"] == 2000.0
    assert attributes["application"] == "domestic"
    assert profile["profile_source"] == "deterministic"


def test_a_thin_description_produces_questions_not_guesses():
    profile = ProductUnderstandingService().analyze("We manufacture heaters.")
    assert profile["missing_fields"], "the platform must ask rather than assume"
    assert all(q["why_it_matters"] for q in profile["missing_fields"])


def test_an_unplaceable_product_is_asked_which_family_it_is():
    profile = ProductUnderstandingService().analyze("We make consumer goods.")
    assert profile["category"] == ""
    assert profile["missing_fields"][0]["field"] == PRODUCT_FAMILY_FIELD
    assert len(profile["missing_fields"]) == 1, "ask the decisive question on its own"


# ---------------------------------------------------------------------------
# LLM-assisted extraction
# ---------------------------------------------------------------------------

def test_llm_enriches_the_profile_but_deterministic_numbers_win(scripted_llm):
    """The model may name the product; it may not overwrite what was written."""
    llm = scripted_llm(
        json.dumps(
            {
                "product_name": "Domestic Electric Storage Water Heater",
                "category": "water-heater",
                # A wrong capacity - the sentence says 15 L.
                "attributes": {"capacity_litres": 99, "installation_type": "Wall mounted (vertical)"},
            }
        )
    )
    profile = ProductUnderstandingService(llm=llm).analyze(
        "We manufacture a 15 litre domestic electric storage water heater at 230 V."
    )

    assert profile["name"] == "Domestic Electric Storage Water Heater"
    assert profile["attributes"]["capacity_litres"] == 15.0, (
        "the number in the user's own words must win over the model's"
    )
    # But a value the text did not carry is accepted.
    assert profile["attributes"]["installation_type"] == "Wall mounted (vertical)"
    assert profile["profile_source"] == "llm+deterministic"
    assert profile["llm_used"] is True


def test_a_category_the_model_invents_is_discarded(scripted_llm):
    llm = scripted_llm(
        json.dumps(
            {"product_name": "Widget", "category": "flux-capacitor", "attributes": {}}
        )
    )
    profile = ProductUnderstandingService(llm=llm).analyze("We make widgets.")
    assert profile["category"] == "", "only the closed category vocabulary is accepted"


def test_attribute_keys_outside_the_schema_are_dropped(scripted_llm):
    llm = scripted_llm(
        json.dumps(
            {
                "product_name": "Heater",
                "category": "water-heater",
                "attributes": {"capacity_litres": 20, "is_bis_certified": True, "nonsense": "x"},
            }
        )
    )
    profile = ProductUnderstandingService(llm=llm).analyze("We make storage water heaters.")
    assert "is_bis_certified" not in profile["attributes"], (
        "a model must not be able to assert certification through the profile"
    )
    assert "nonsense" not in profile["attributes"]
    assert set(profile["attributes"]) <= ALLOWED_ATTRIBUTE_KEYS | {"working_pressure_kpa"}


def test_unusable_model_output_falls_back_to_deterministic(scripted_llm):
    profile = ProductUnderstandingService(llm=scripted_llm("garbage")).analyze(
        "We manufacture a 15 litre storage water heater."
    )
    assert profile["attributes"]["capacity_litres"] == 15.0
    assert profile["profile_source"] == "deterministic"
    assert any("did not return a usable profile" in n for n in profile["notes"])


# ---------------------------------------------------------------------------
# Interview rounds
# ---------------------------------------------------------------------------

def test_round_one_asks_only_the_decisive_questions():
    questions = ProductInterviewService().build_questions(
        "water-heater", {"power_source": "electric"}
    )
    assert questions
    assert all(q["priority"] == 1 for q in questions)
    assert len(questions) <= MAX_QUESTIONS
    fields = {q["field"] for q in questions}
    assert "heater_type" in fields
    # Round-2 detail must not appear while round 1 is outstanding.
    assert "installation_type" not in fields


def test_round_two_follows_once_the_decisive_answers_are_in():
    answered = {
        "power_source": "electric", "heater_type": "Storage water heater",
        "capacity_litres": 15, "voltage_v": 230, "application": "domestic",
    }
    questions = ProductInterviewService().build_questions("water-heater", answered)
    assert questions, "there is still useful detail to collect"
    assert all(q["priority"] == 2 for q in questions)
    assert {"power_w", "installation_type", "inner_container_material"} == {
        q["field"] for q in questions
    }


def test_the_interview_ends_when_everything_is_known():
    complete = {
        "power_source": "electric", "heater_type": "Storage water heater",
        "capacity_litres": 15, "voltage_v": 230, "application": "domestic",
        "power_w": 2000, "installation_type": "Floor standing",
        "inner_container_material": "Stainless steel",
    }
    assert ProductInterviewService().build_questions("water-heater", complete) == []


@pytest.mark.parametrize("category", ["water-heater", "pressure-cooker", "toy", "helmet"])
def test_every_round_is_short_enough_to_answer(category):
    for priority in range(1, max_priority_for(category) + 1):
        assert len(field_specs_for(category, priority)) <= 6


@pytest.mark.parametrize(
    "category,expected",
    [
        ("water-heater", "heater_type"),
        ("pressure-cooker", "body_material"),
        ("toy", "age_group_min_months"),
        ("helmet", "helmet_type"),
    ],
)
def test_questions_are_category_specific_not_generic(category, expected):
    fields = {q["field"] for q in ProductInterviewService().build_questions(category, {})}
    assert expected in fields


def test_questions_for_one_category_never_leak_into_another():
    toy = {q["field"] for q in ProductInterviewService().build_questions("toy", {})}
    helmet = {q["field"] for q in ProductInterviewService().build_questions("helmet", {})}
    assert not (toy & helmet), "a toy must never be asked about shell material"


# ---------------------------------------------------------------------------
# Answer normalisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("capacity_litres", "15", 15.0),
        ("voltage_v", "230 V single phase", 230.0),
        ("application", "Domestic / household", "domestic"),
        ("age_group_min_months", "Under 18 months", 12),
        ("has_small_parts", "Yes", True),
        ("has_cords", "No", False),
        ("protection_class", "Class I (earthed)", "I"),
        ("thermal_cutout_reset_type", "manual", "manual"),
    ],
)
def test_free_text_answers_normalise_to_canonical_values(field, value, expected):
    assert normalise_answer(field, value) == (field, expected)


def test_not_sure_is_recorded_as_unknown_not_as_a_value():
    assert normalise_answer("has_small_parts", "Not sure") == ("has_small_parts", None)


def test_family_answers_map_back_onto_taxonomy_keys():
    resolve = ProductInterviewService.resolve_family_answer
    assert resolve("Electric Water Heater") == "water-heater"
    assert resolve("Pressure Cooker") == "pressure-cooker"
    assert resolve("toy") == "toy"
    assert resolve("something else entirely") == ""
