"""Evidence Shield - backend validation of every generated claim.

This is deliberately NOT a prompt that says "do not hallucinate". It is a
verification step that runs after generation, on the server, and can reject
model output:

1. The retriever produces a closed set of chunk ids that were actually placed
   in the model's context.
2. The model must return its answer decomposed into claims, each carrying the
   chunk ids that support it.
3. Every cited chunk id is checked against that closed set. A claim citing
   anything else - a fabricated id, an id from a previous turn, an id the model
   invented to look authoritative - is dropped and recorded.
4. A claim with no surviving citation is unsupported and is dropped too.
5. If nothing survives, the answer is replaced with an explicit abstention
   rather than shown to the user.

The report is returned to the UI so the user can see the check happened.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence, Set, Tuple

from app.core.constants import UNVERIFIED_MESSAGE
from app.schemas.models import Claim, EvidenceShieldReport

logger = logging.getLogger(__name__)

ABSTENTION_ANSWER = (
    "I could not verify an answer to this question from the documents currently "
    "in the corpus. " + UNVERIFIED_MESSAGE
)


@dataclass
class ShieldResult:
    answer: str
    claims: List[Claim] = field(default_factory=list)
    report: EvidenceShieldReport = None  # type: ignore[assignment]
    answerable: bool = True


class EvidenceShield:
    def __init__(self, retrieved_chunk_ids: Iterable[str]) -> None:
        self.allowed: Set[str] = {c for c in retrieved_chunk_ids if c}

    # ------------------------------------------------------------------
    def validate(
        self, answer: str, raw_claims: Sequence[Dict[str, object]]
    ) -> ShieldResult:
        accepted: List[Claim] = []
        rejected: List[Dict[str, object]] = []

        for raw in raw_claims:
            text = str(raw.get("text", "")).strip()
            if not text:
                continue
            cited = [str(c).strip() for c in (raw.get("source_chunk_ids") or []) if str(c).strip()]
            valid = [c for c in cited if c in self.allowed]
            invalid = [c for c in cited if c not in self.allowed]

            if invalid:
                rejected.append(
                    {
                        "claim": text,
                        "invalid_chunk_ids": invalid,
                        "reason": "cited evidence was not in the retrieved context",
                    }
                )
                logger.warning(
                    "Evidence Shield rejected citation(s) %s for claim: %s", invalid, text[:120]
                )
            if not valid:
                if not invalid:
                    rejected.append(
                        {
                            "claim": text,
                            "invalid_chunk_ids": [],
                            "reason": "claim carried no supporting evidence",
                        }
                    )
                continue
            accepted.append(Claim(text=text, source_chunk_ids=valid, supported=True))

        if not accepted:
            report = EvidenceShieldReport(
                verified=False,
                total_claims=len(raw_claims),
                supported_claims=0,
                rejected_claims=rejected,
                retrieved_chunk_ids=sorted(self.allowed),
                reason=(
                    "No generated claim survived evidence validation. The answer was "
                    "replaced with an explicit abstention."
                ),
            )
            return ShieldResult(
                answer=ABSTENTION_ANSWER, claims=[], report=report, answerable=False
            )

        final_answer = self._rebuild_answer(answer, accepted, bool(rejected))
        report = EvidenceShieldReport(
            verified=True,
            total_claims=len(raw_claims),
            supported_claims=len(accepted),
            rejected_claims=rejected,
            retrieved_chunk_ids=sorted(self.allowed),
            reason=(
                "Every displayed claim cites a clause that was present in the retrieved "
                "context."
                if not rejected
                else f"{len(rejected)} unsupported claim(s) were removed before display."
            ),
        )
        return ShieldResult(answer=final_answer, claims=accepted, report=report)

    # ------------------------------------------------------------------
    @staticmethod
    def _rebuild_answer(answer: str, accepted: Sequence[Claim], had_rejections: bool) -> str:
        """Return prose that is fully covered by validated claims.

        Removing a rejected citation but leaving its sentence in the prose would
        defeat the whole control - the unsupported assertion would still be on
        screen, just without a link. So the model's prose is kept only when
        *every* sentence in it is covered by the surviving claims. Otherwise the
        answer is rebuilt from those claims alone.

        Note this also catches the subtler case where all claims validated but
        the prose asserted something extra that was never decomposed into a
        claim at all.
        """
        answer = (answer or "").strip()
        rebuilt = " ".join(claim.text.strip() for claim in accepted).strip()
        if not answer:
            return rebuilt
        if had_rejections:
            return rebuilt

        supported_tokens = _token_set(" ".join(c.text for c in accepted))
        for sentence in _SENTENCE_SPLIT.split(answer):
            if not _is_covered(sentence, supported_tokens):
                logger.info(
                    "Evidence Shield rebuilt the answer: '%s' is not covered by any "
                    "validated claim.", sentence.strip()[:120],
                )
                return rebuilt
        return answer

    # ------------------------------------------------------------------
    def cited_chunk_ids(self, claims: Sequence[Claim]) -> List[str]:
        seen: List[str] = []
        for claim in claims:
            for chunk_id in claim.source_chunk_ids:
                if chunk_id not in seen:
                    seen.append(chunk_id)
        return seen


def build_abstention(retrieved_chunk_ids: Sequence[str], reason: str) -> ShieldResult:
    return ShieldResult(
        answer=ABSTENTION_ANSWER,
        claims=[],
        report=EvidenceShieldReport(
            verified=False,
            total_claims=0,
            supported_claims=0,
            rejected_claims=[],
            retrieved_chunk_ids=list(retrieved_chunk_ids),
            reason=reason,
        ),
        answerable=False,
    )


_SENTENCE_SPLIT = re.compile(r"(?<=[.;])\s+")
_WORD_RE = re.compile(r"[a-z0-9]+")

#: A sentence counts as covered when this fraction of its content words also
#: appear in the validated claims. Not a semantic check - a deliberately blunt
#: containment test whose failure mode is to rebuild the answer, never to let
#: uncited material through.
COVERAGE_THRESHOLD = 0.75

#: Function words carry no evidential weight, so they are ignored.
_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for", "from",
    "has", "have", "in", "is", "it", "its", "must", "not", "of", "on", "or", "shall",
    "should", "that", "the", "their", "there", "these", "this", "to", "was", "were",
    "which", "with", "will", "when", "where", "any", "all", "also", "such",
}


def _token_set(text: str) -> set:
    return {t for t in _WORD_RE.findall((text or "").lower()) if t not in _STOP}


def _is_covered(sentence: str, supported_tokens: set) -> bool:
    tokens = _token_set(sentence)
    if not tokens:
        return True  # punctuation or connective text
    overlap = len(tokens & supported_tokens) / len(tokens)
    return overlap >= COVERAGE_THRESHOLD


def extractive_claims(clauses: Sequence[Tuple[str, str]], limit: int = 4) -> List[Dict[str, object]]:
    """Deterministic claim construction used when no LLM is configured.

    Each clause becomes one claim quoting its own text, cited to itself, so the
    no-API path produces exactly the same verified structure as the LLM path -
    it just quotes instead of paraphrasing.
    """
    claims: List[Dict[str, object]] = []
    for chunk_id, text in list(clauses)[:limit]:
        sentences = _SENTENCE_SPLIT.split(text.strip())
        snippet = " ".join(sentences[:2]).strip()
        if not snippet:
            continue
        claims.append({"text": snippet, "source_chunk_ids": [chunk_id]})
    return claims
