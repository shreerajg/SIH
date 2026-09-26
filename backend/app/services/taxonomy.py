"""Product taxonomy: category detection and the attributes that matter.

This is the deterministic backbone of product understanding. It gives the
platform a usable product profile with no LLM at all, and it gives the LLM a
closed vocabulary to work inside when one is available - the model classifies
into these categories, it does not invent new ones.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.text_utils import content_tokens


@dataclass
class FieldSpec:
    field: str
    question: str
    why_it_matters: str
    options: List[str] = field(default_factory=list)
    input_type: str = "choice"   # choice | number | text | boolean
    unit: Optional[str] = None
    required: bool = True
    #: 1 = decisive for which standards apply, asked first.
    #: 2 = useful for the gap analysis, asked only once round 1 is answered.
    #: Splitting them is what keeps a round to 3-5 questions instead of a form.
    priority: int = 1


@dataclass
class CategorySpec:
    key: str
    label: str
    #: Strong signals - a single hit is decisive.
    primary_terms: List[str]
    #: Weak signals - contribute to the score.
    secondary_terms: List[str] = field(default_factory=list)
    #: Terms that rule the category out.
    negative_terms: List[str] = field(default_factory=list)
    fields: List[FieldSpec] = field(default_factory=list)
    #: Defaults applied only when the description supports them.
    implied_attributes: Dict[str, Any] = field(default_factory=dict)


CATEGORIES: List[CategorySpec] = [
    CategorySpec(
        key="water-heater",
        label="Electric Water Heater",
        primary_terms=["water heater", "storage water heater", "geyser", "storage geyser",
                       "instant water heater", "immersion heater"],
        secondary_terms=["heater", "hot water", "litre", "tank", "thermostat", "heating element"],
        negative_terms=["room heater", "space heater", "solar"],
        fields=[
            FieldSpec(
                field="heater_type",
                question="What type of water heater is it?",
                why_it_matters="Storage and instantaneous heaters are covered by different standards; this prototype's corpus covers storage type.",
                options=["Storage water heater", "Instant / instantaneous water heater",
                         "Immersion rod", "Solar water heater"],
            ),
            FieldSpec(
                field="capacity_litres",
                question="What is the rated storage capacity in litres?",
                why_it_matters="Scope clauses and wall-thickness style requirements are capacity dependent.",
                input_type="number", unit="L",
            ),
            FieldSpec(
                field="voltage_v",
                question="What is the rated supply voltage?",
                why_it_matters="Voltage determines whether the household appliance safety standards apply.",
                options=["230 V single phase", "415 V three phase", "Other"],
                input_type="number", unit="V",
            ),
            FieldSpec(
                field="application",
                question="Where will the product be used?",
                why_it_matters="Domestic and industrial appliances fall under different scopes.",
                options=["Domestic / household", "Commercial", "Industrial"],
            ),
            FieldSpec(
                field="power_w",
                question="What is the rated power input?",
                why_it_matters="Power input drives the supply-cord sizing and the conditions of the temperature rise test.",
                input_type="number", unit="W", priority=2,
            ),
            FieldSpec(
                field="installation_type",
                question="How is the appliance installed?",
                why_it_matters="Mounting affects the stability and pressure-relief requirements that apply.",
                options=["Wall mounted (vertical)", "Wall mounted (horizontal)", "Floor standing"],
                priority=2,
            ),
            FieldSpec(
                field="inner_container_material",
                question="What is the inner container made from?",
                why_it_matters="The corrosion-protection clause is assessed against this declared material.",
                options=[
                    "Vitreous enamel coated mild steel",
                    "Stainless steel",
                    "Epoxy coated mild steel",
                    "Copper",
                ],
                input_type="text", priority=2,
            ),
        ],
        implied_attributes={"power_source": "electric"},
    ),
    CategorySpec(
        key="pressure-cooker",
        label="Pressure Cooker",
        primary_terms=["pressure cooker", "pressure pan", "cooker"],
        secondary_terms=["aluminium", "stainless steel", "gasket", "vent weight",
                         "safety valve", "kitchen", "cookware"],
        negative_terms=["rice cooker", "induction cooktop"],
        fields=[
            FieldSpec(
                field="capacity_litres",
                question="What is the nominal capacity in litres?",
                why_it_matters="Body and base thickness requirements change with capacity.",
                input_type="number", unit="L",
            ),
            FieldSpec(
                field="body_material",
                question="What is the body made from?",
                why_it_matters="Material determines the applicable material and thickness clauses.",
                options=["Aluminium", "Stainless steel", "Hard anodised aluminium"],
            ),
            FieldSpec(
                field="operating_pressure_kpa",
                question="What is the declared operating pressure?",
                why_it_matters="Safety device release pressures and the burst test are multiples of this value.",
                input_type="number", unit="kPa",
            ),
            FieldSpec(
                field="application",
                question="Is it for domestic or commercial use?",
                why_it_matters="The demo specification covers domestic cooking only.",
                options=["Domestic / household", "Commercial catering"],
            ),
        ],
    ),
    CategorySpec(
        key="toy",
        label="Toy",
        primary_terms=["toy", "toys", "rattle", "soft toy", "stuffed toy", "doll",
                       "building blocks", "ride-on toy", "ride on toy"],
        secondary_terms=["children", "kids", "play", "plastic toy", "plush", "puzzle"],
        negative_terms=["sports equipment", "bicycle"],
        fields=[
            FieldSpec(
                field="age_group_min_months",
                question="What is the minimum age the toy is intended for?",
                why_it_matters="Small-part and cord-length requirements only apply below certain ages.",
                options=["Under 18 months", "18 to 36 months", "36 months and above",
                         "8 years and above"],
            ),
            FieldSpec(
                field="toy_materials",
                question="Which materials are used?",
                why_it_matters="Each material and colour needs its own chemical migration assessment.",
                options=["Plastic (ABS/PP/PVC)", "Painted wood", "Textile / plush",
                         "Metal", "Mixed materials"],
                input_type="text",
            ),
            FieldSpec(
                field="has_small_parts",
                question="Does the toy contain or can it release small parts?",
                why_it_matters="Small parts drive the choking-hazard requirements and warnings.",
                options=["Yes", "No", "Not sure"],
                input_type="boolean",
            ),
            FieldSpec(
                field="has_cords",
                question="Does the toy have cords, strings or elastics?",
                why_it_matters="Cord length limits apply to toys for younger children.",
                options=["Yes", "No"],
                input_type="boolean", required=False,
            ),
        ],
    ),
    CategorySpec(
        key="helmet",
        label="Protective Helmet",
        primary_terms=["helmet", "protective helmet", "crash helmet", "motorcycle helmet"],
        secondary_terms=["two wheeler", "rider", "visor", "shell", "chin strap", "eps"],
        negative_terms=["bicycle helmet", "industrial helmet", "hard hat"],
        fields=[
            FieldSpec(
                field="helmet_type",
                question="What type of helmet is it?",
                why_it_matters="Mass limits and field-of-vision requirements differ by helmet type.",
                options=["Full face", "Open face", "Half coverage"],
            ),
            FieldSpec(
                field="shell_material",
                question="What is the shell made from?",
                why_it_matters="Shell material is a declared and certificated construction property.",
                options=["ABS thermoplastic", "Polycarbonate", "Fibre reinforced composite"],
            ),
            FieldSpec(
                field="mass_kg",
                question="What is the mass of the complete helmet?",
                why_it_matters="The specification sets a maximum helmet mass by type.",
                input_type="number", unit="kg",
            ),
            FieldSpec(
                field="has_visor",
                question="Is a visor fitted?",
                why_it_matters="A fitted visor brings luminous-transmittance requirements into scope.",
                options=["Yes", "No"], input_type="boolean", required=False,
            ),
        ],
    ),
    CategorySpec(
        key="electrical-appliance",
        label="Electrical Appliance (general)",
        primary_terms=["electrical appliance", "household appliance", "mixer grinder",
                       "electric kettle", "induction cooktop", "room heater", "fan",
                       "iron", "toaster"],
        secondary_terms=["electric", "voltage", "watt", "appliance", "230 v", "mains"],
        fields=[
            FieldSpec(
                field="appliance_type",
                question="What kind of appliance is it?",
                why_it_matters="The product-specific standard depends on the appliance family.",
                input_type="text",
            ),
            FieldSpec(
                field="voltage_v",
                question="What is the rated supply voltage?",
                why_it_matters="Household appliance safety standards are scoped by voltage.",
                input_type="number", unit="V",
            ),
            FieldSpec(
                field="power_w",
                question="What is the rated power input?",
                why_it_matters="Power input drives cord sizing and temperature-rise conditions.",
                input_type="number", unit="W",
            ),
            FieldSpec(
                field="protection_class",
                question="Is the appliance Class I (earthed) or Class II (double insulated)?",
                why_it_matters="This determines whether earthing or reinforced-insulation clauses apply.",
                options=["Class I (earthed)", "Class II (double insulated)"],
            ),
        ],
        implied_attributes={"power_source": "electric"},
    ),
]

CATEGORY_BY_KEY = {c.key: c for c in CATEGORIES}

#: Maps a detected category to the corpus product_category values it favours.
CATEGORY_TO_CORPUS = {
    "water-heater": "electrical-appliance",
    "electrical-appliance": "electrical-appliance",
    "pressure-cooker": "kitchenware",
    "toy": "toys",
    "helmet": "personal-protective-equipment",
}

APPLICATION_TERMS = {
    "domestic": ["domestic", "household", "home", "residential", "consumer"],
    "commercial": ["commercial", "catering", "hotel", "restaurant", "office"],
    "industrial": ["industrial", "factory", "process", "plant"],
}

POWER_SOURCE_TERMS = {
    "electric": ["electric", "electrical", "mains", "230 v", "240 v", "plug"],
    "gas": ["gas", "lpg", "png"],
    "solar": ["solar"],
    "manual": ["manual", "hand operated"],
}


def _singularise(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("es") and not token.endswith("ses"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def detect_category(text: str) -> Dict[str, Any]:
    """Score every category against the description. Deterministic, explainable."""
    lowered = (text or "").lower()
    raw_tokens = content_tokens(text)
    tokens = set(raw_tokens) | {_singularise(t) for t in raw_tokens}
    scored: List[Dict[str, Any]] = []

    for spec in CATEGORIES:
        if any(term in lowered for term in spec.negative_terms):
            negative_hit = True
        else:
            negative_hit = False
        primary_hits = [t for t in spec.primary_terms if t in lowered]
        secondary_hits = [
            t for t in spec.secondary_terms
            if (t in lowered if " " in t else t in tokens)
        ]
        score = 3.0 * len(primary_hits) + 0.6 * len(secondary_hits)
        if negative_hit and not primary_hits:
            score = 0.0
        if score > 0:
            scored.append(
                {
                    "key": spec.key,
                    "label": spec.label,
                    "score": round(score, 3),
                    "primary_hits": primary_hits,
                    "secondary_hits": secondary_hits,
                }
            )

    scored.sort(key=lambda s: -s["score"])
    best = scored[0] if scored else None
    return {
        "category": best["key"] if best else "",
        "label": best["label"] if best else "",
        "confidence": "high" if best and best["primary_hits"] else ("low" if best else "none"),
        "ranked": scored[:4],
    }


def detect_from_terms(text: str, mapping: Dict[str, List[str]]) -> str:
    lowered = (text or "").lower()
    for value, terms in mapping.items():
        if any(term in lowered for term in terms):
            return value
    return ""


def field_specs_for(category: str, priority: Optional[int] = None) -> List[FieldSpec]:
    spec = CATEGORY_BY_KEY.get(category)
    if spec is None:
        return []
    fields = list(spec.fields)
    if priority is not None:
        fields = [f for f in fields if f.priority == priority]
    return fields


def max_priority_for(category: str) -> int:
    fields = field_specs_for(category)
    return max((f.priority for f in fields), default=1)
