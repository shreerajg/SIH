"""ProductInterviewService - targeted follow-up questions, never a guess.

When the description is too thin to act on ("we manufacture heaters"), the
platform does not pick a standard anyway. It asks a small number of decisive
questions, in priority order:

1. Which product family is this?  (only when the category is ambiguous)
2. The required attributes of that family that are still unknown.

The interview is capped so it never becomes an interrogation, and the user can
always say "continue with current information".
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.llm.service import LLMService, get_llm
from app.schemas.models import MissingField
from app.services.taxonomy import (
    CATEGORIES,
    CATEGORY_BY_KEY,
    field_specs_for,
    max_priority_for,
)

MAX_QUESTIONS = 4

PRODUCT_FAMILY_FIELD = "product_family"

FAMILY_LABEL_TO_KEY = {spec.label.lower(): spec.key for spec in CATEGORIES}


class ProductInterviewService:
    def __init__(self, llm: Optional[LLMService] = None) -> None:
        self.llm = llm or get_llm()

    def build_questions(
        self, category: str, attributes: Dict[str, Any], detection: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """The next round of questions, never more than MAX_QUESTIONS.

        Rounds are ordered by how much the answer changes: priority 1 decides
        *which standards apply* and is asked first; priority 2 only sharpens the
        gap analysis and is asked once the decisive answers are in. Asking all of
        them at once turns an interview into a form, which is what makes people
        abandon it.
        """
        if not category:
            return [self._family_question(detection)]

        for priority in range(1, max_priority_for(category) + 1):
            questions = self._round(category, attributes, priority)
            if questions:
                return questions
        return []

    @staticmethod
    def _round(
        category: str, attributes: Dict[str, Any], priority: int
    ) -> List[Dict[str, Any]]:
        questions: List[Dict[str, Any]] = []
        for spec in field_specs_for(category, priority):
            if len(questions) >= MAX_QUESTIONS:
                break
            if priority == 1 and not spec.required:
                continue
            if attributes.get(spec.field) not in (None, "", []):
                continue
            questions.append(
                MissingField(
                    field=spec.field,
                    question=spec.question,
                    why_it_matters=spec.why_it_matters,
                    options=spec.options,
                    input_type=spec.input_type,
                    unit=spec.unit,
                    priority=priority,
                ).model_dump()
            )
        return questions

    @staticmethod
    def _family_question(detection: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        ranked = (detection or {}).get("ranked") or []
        ordered_keys = [r["key"] for r in ranked]
        options: List[str] = []
        for key in ordered_keys:
            spec = CATEGORY_BY_KEY.get(key)
            if spec and spec.label not in options:
                options.append(spec.label)
        for spec in CATEGORIES:
            if spec.label not in options:
                options.append(spec.label)
        return MissingField(
            field=PRODUCT_FAMILY_FIELD,
            question="Which of these best describes the product?",
            why_it_matters=(
                "The description does not identify the product family clearly enough to "
                "search the standards corpus. Choosing the family narrows the search "
                "instead of guessing."
            ),
            options=options,
            input_type="choice",
        ).model_dump()

    @staticmethod
    def resolve_family_answer(value: Any) -> str:
        """Map a family answer back onto a taxonomy key."""
        if not isinstance(value, str):
            return ""
        lowered = value.strip().lower()
        if lowered in CATEGORY_BY_KEY:
            return lowered
        if lowered in FAMILY_LABEL_TO_KEY:
            return FAMILY_LABEL_TO_KEY[lowered]
        for label, key in FAMILY_LABEL_TO_KEY.items():
            if lowered in label or label in lowered:
                return key
        return ""
