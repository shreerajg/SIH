"""ProductUnderstandingService - free text in, structured product profile out.

Two paths run and are merged:

1. A deterministic path (taxonomy + regex quantity extraction) that always
   works, with or without an LLM.
2. An optional LLM path constrained to the closed category vocabulary and
   validated through Pydantic.

Where the two disagree on a number, the deterministic extraction wins - it is
reading the user's own words, not paraphrasing them.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.text_utils import coerce_number, extract_numeric_attributes, truncate
from app.llm.service import LLMService, get_llm
from app.models import Product
from app.schemas.models import MissingField
from app.services.taxonomy import (
    APPLICATION_TERMS,
    CATEGORY_BY_KEY,
    POWER_SOURCE_TERMS,
    detect_category,
    detect_from_terms,
    field_specs_for,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a standards analyst building a structured product profile from a "
    "manufacturer's plain-English description. You classify and extract only. "
    "You never name a standard, never state a regulatory status, and never "
    "invent a value the description does not support. If a value is absent, "
    "omit it rather than guessing."
)


class _LLMProductProfile(BaseModel):
    product_name: str = Field(description="Short, specific product name")
    category: str = Field(
        description="EXACTLY one of: water-heater, pressure-cooker, toy, helmet, "
                    "electrical-appliance, or empty string if none apply"
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Only attributes explicitly supported by the description, "
                    "using snake_case keys such as capacity_litres, voltage_v, "
                    "power_w, application, body_material, age_group_min_months",
    )


ALLOWED_CATEGORIES = set(CATEGORY_BY_KEY.keys())

#: Attribute keys accepted from a model. Anything else is discarded so the
#: profile schema cannot drift.
ALLOWED_ATTRIBUTE_KEYS = {
    "capacity_litres", "voltage_v", "power_w", "frequency_hz", "pressure_bar",
    "pressure_kpa", "operating_pressure_kpa", "temperature_c", "mass_kg",
    "application", "power_source", "heater_type", "appliance_type",
    "body_material", "base_thickness_mm", "body_thickness_mm",
    "age_group_min_months", "toy_materials", "has_small_parts", "has_cords",
    "cord_length_mm", "helmet_type", "shell_material", "has_visor",
    "protection_class", "inner_container_material", "product_variant",
    "max_water_temperature_c", "thermal_cutout_fitted",
    "pressure_relief_device_fitted", "supply_cord_csa_mm2",
    "primary_regulator_type", "secondary_safety_device_fitted",
    "lid_interlock_fitted", "liner_density_kg_m3", "peripheral_vision_deg",
    "visor_transmittance_percent", "earthing_terminal_provided",
    "anode_inspection_interval_months", "thermal_cutout_reset_type",
    "earth_continuity_ohm", "insulation_resistance_mohm", "installation_type",
}

AGE_LABEL_TO_MONTHS = {
    "under 18 months": 12,
    "18 to 36 months": 18,
    "36 months and above": 36,
    "8 years and above": 96,
}


class ProductUnderstandingService:
    def __init__(self, llm: Optional[LLMService] = None) -> None:
        self.llm = llm or get_llm()

    # ------------------------------------------------------------------
    def analyze(self, description: str, name: Optional[str] = None) -> Dict[str, Any]:
        deterministic = self._deterministic_profile(description)
        notes: List[str] = []
        llm_used = False

        llm_profile = self._llm_profile(description) if self.llm.available else None
        if llm_profile is not None:
            llm_used = True
            merged = self._merge(deterministic, llm_profile)
        else:
            merged = deterministic
            if not self.llm.available:
                notes.append(
                    "Running without an LLM key: the product profile was built by the "
                    "deterministic taxonomy and quantity extractor."
                )
            else:
                notes.append(
                    "The language model did not return a usable profile; the deterministic "
                    "extraction is shown instead."
                )

        if name:
            merged["name"] = name
        if not merged.get("category"):
            notes.append(
                "The product could not be matched to a category the current corpus covers. "
                "Answer the follow-up questions or add more detail."
            )

        from app.services.product_interview import ProductInterviewService

        merged["missing_fields"] = ProductInterviewService(self.llm).build_questions(
            merged.get("category", ""),
            merged.get("attributes", {}),
            merged.get("detection"),
        )
        merged["profile_source"] = "llm+deterministic" if llm_used else "deterministic"
        merged["notes"] = notes
        merged["llm_used"] = llm_used
        return merged

    # ------------------------------------------------------------------
    def _deterministic_profile(self, description: str) -> Dict[str, Any]:
        detection = detect_category(description)
        attributes: Dict[str, Any] = {}
        attributes.update(extract_numeric_attributes(description))

        application = detect_from_terms(description, APPLICATION_TERMS)
        if application:
            attributes["application"] = application
        power_source = detect_from_terms(description, POWER_SOURCE_TERMS)
        if power_source:
            attributes["power_source"] = power_source

        category = detection["category"]
        spec = CATEGORY_BY_KEY.get(category)
        if spec:
            for key, value in spec.implied_attributes.items():
                attributes.setdefault(key, value)

        # Category-specific refinements.
        lowered = (description or "").lower()
        if category == "water-heater":
            if "instant" in lowered or "instantaneous" in lowered:
                attributes["heater_type"] = "Instant / instantaneous water heater"
            elif "storage" in lowered or "geyser" in lowered:
                attributes["heater_type"] = "Storage water heater"
            if "pressure_kpa" in attributes:
                attributes.setdefault("working_pressure_kpa", attributes.pop("pressure_kpa"))
        if category == "pressure-cooker":
            if "stainless" in lowered:
                attributes["body_material"] = "Stainless steel"
            elif "hard anodis" in lowered or "hard anodiz" in lowered:
                attributes["body_material"] = "Hard anodised aluminium"
            elif "aluminium" in lowered or "aluminum" in lowered:
                attributes["body_material"] = "Aluminium"
            if "pressure_kpa" in attributes:
                attributes["operating_pressure_kpa"] = attributes.pop("pressure_kpa")
            elif "pressure_bar" in attributes:
                attributes["operating_pressure_kpa"] = float(attributes.pop("pressure_bar")) * 100
        if category == "helmet":
            if "full face" in lowered or "full-face" in lowered:
                attributes["helmet_type"] = "Full face"
            elif "open face" in lowered or "open-face" in lowered:
                attributes["helmet_type"] = "Open face"
            elif "half" in lowered:
                attributes["helmet_type"] = "Half coverage"
            if "abs" in lowered:
                attributes["shell_material"] = "ABS thermoplastic"
            elif "polycarbonate" in lowered:
                attributes["shell_material"] = "Polycarbonate"
        if category == "toy":
            months = attributes.pop("age_group_min_years", None)
            if months is not None:
                attributes["age_group_min_months"] = int(float(months) * 12)
            elif "month" in lowered:
                import re as _re

                match = _re.search(r"(\d+)\s*month", lowered)
                if match:
                    attributes["age_group_min_months"] = int(match.group(1))

        name = self._derive_name(description, detection)
        return {
            "name": name,
            "category": category,
            "category_label": detection["label"],
            "attributes": attributes,
            "detection": detection,
            "description": description.strip(),
        }

    @staticmethod
    def _derive_name(description: str, detection: Dict[str, Any]) -> str:
        best = detection["ranked"][0] if detection["ranked"] else None
        if best and best["primary_hits"]:
            return best["primary_hits"][0].title()
        if best:
            # Matched only on weak signals: name it after the family rather than
            # echoing the sentence back ("We manufacture heaters." is not a name).
            return best["label"]
        return truncate(description, 60) or "Unnamed product"

    # ------------------------------------------------------------------
    def _llm_profile(self, description: str) -> Optional[Dict[str, Any]]:
        prompt = (
            "Manufacturer description:\n"
            f"\"\"\"{description.strip()[:3000]}\"\"\"\n\n"
            "Extract the product profile. The category MUST be one of: "
            f"{', '.join(sorted(ALLOWED_CATEGORIES))} (or an empty string). "
            "Only include attributes the description actually supports."
        )
        result = self.llm.structured(SYSTEM_PROMPT, prompt, _LLMProductProfile)
        if result is None:
            return None
        category = (result.category or "").strip().lower()
        if category not in ALLOWED_CATEGORIES:
            category = ""
        attributes = {
            k: v for k, v in (result.attributes or {}).items()
            if k in ALLOWED_ATTRIBUTE_KEYS and v not in (None, "", [])
        }
        return {
            "name": (result.product_name or "").strip(),
            "category": category,
            "attributes": attributes,
        }

    @staticmethod
    def _merge(deterministic: Dict[str, Any], llm: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(deterministic)
        if llm.get("name"):
            merged["name"] = llm["name"]
        if not merged.get("category") and llm.get("category"):
            merged["category"] = llm["category"]
            merged["category_label"] = CATEGORY_BY_KEY[llm["category"]].label
        attributes = dict(llm.get("attributes") or {})
        # Deterministic values are authoritative: they came from the literal text.
        attributes.update(deterministic.get("attributes") or {})
        merged["attributes"] = attributes
        return merged

    # ------------------------------------------------------------------
    @staticmethod
    def _missing_fields(category: str, attributes: Dict[str, Any]) -> List[Dict[str, Any]]:
        missing: List[Dict[str, Any]] = []
        for spec in field_specs_for(category):
            if not spec.required:
                continue
            value = attributes.get(spec.field)
            if value in (None, "", []):
                missing.append(
                    MissingField(
                        field=spec.field,
                        question=spec.question,
                        why_it_matters=spec.why_it_matters,
                        options=spec.options,
                        input_type=spec.input_type,
                        unit=spec.unit,
                    ).model_dump()
                )
        return missing[:4]

    # ------------------------------------------------------------------
    def persist(self, db: Session, profile: Dict[str, Any]) -> Product:
        product = Product(
            id=f"prd-{uuid.uuid4().hex[:12]}",
            name=profile.get("name") or "Unnamed product",
            description=profile.get("description", ""),
            category=profile.get("category", ""),
            attributes_json=profile.get("attributes", {}),
            missing_fields_json=profile.get("missing_fields", []),
            profile_source=profile.get("profile_source", "deterministic"),
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product


def normalise_answer(field_name: str, value: Any) -> Tuple[str, Any]:
    """Coerce an interview answer into the canonical attribute representation."""
    if isinstance(value, str):
        stripped = value.strip()
        lowered = stripped.lower()
        if field_name == "age_group_min_months" and lowered in AGE_LABEL_TO_MONTHS:
            return field_name, AGE_LABEL_TO_MONTHS[lowered]
        if field_name.endswith(("_litres", "_v", "_w", "_kg", "_kpa", "_mm", "_ohm",
                                "_mohm", "_mm2", "_percent", "_deg", "_months")):
            number = coerce_number(stripped)
            if number is not None:
                return field_name, number
        if lowered in ("yes", "true"):
            return field_name, True
        if lowered in ("no", "false"):
            return field_name, False
        if lowered == "not sure":
            return field_name, None
        if field_name == "application":
            for key, terms in APPLICATION_TERMS.items():
                if any(term in lowered for term in terms):
                    return field_name, key
        if field_name == "protection_class":
            if "class i" in lowered and "class ii" not in lowered:
                return field_name, "I"
            if "class ii" in lowered:
                return field_name, "II"
        return field_name, stripped
    return field_name, value
