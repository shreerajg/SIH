"""Conversation state for grounded multi-turn Q&A.

The naive approach - concatenate every previous turn and send it to retrieval -
degrades quickly: earlier questions drag retrieval toward whatever they were
about, and the context window fills with text that is not evidence.

Instead only what is needed to *resolve a follow-up* is carried:

* ``selected_product_id`` / ``selected_standard_ids`` - the scope the user is
  working in, so "why is this test necessary?" stays on the same standard;
* ``last_retrieved_chunk_ids`` and ``last_answer_summary`` - so a pronoun
  ("this test", "that clause") can be resolved to something concrete;
* a short rolling summary of the exchange, never the full transcript.

Follow-up detection is deterministic. A question that names its own subject is
treated as a fresh query even mid-conversation, so context can never silently
override what the user actually asked.
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.text_utils import extract_is_numbers, truncate

#: Conversations older than this are dropped. A prototype does not need a
#: durable store for chat scrollback.
TTL_SECONDS = 60 * 60
MAX_TURNS = 12
MAX_CONVERSATIONS = 200

#: A question that opens with one of these, and names no subject of its own,
#: is a follow-up about the previous turn.
_FOLLOW_UP_OPENERS = re.compile(
    r"^\s*(and|also|what about|how about|why|why is|why are|why does|what does that|"
    r"is it|are they|does it|do they|can it|which one|the same|then|so)\b",
    re.IGNORECASE,
)
#: Pronouns with no antecedent in the question itself.
_DANGLING_REFERENCE = re.compile(
    r"\b(it|its|this|that|these|those|them|they|the test|the clause|the standard|"
    r"the requirement|the same)\b",
    re.IGNORECASE,
)
#: Words that mean the user has named a subject, so it is not a follow-up.
_SELF_CONTAINED = re.compile(
    r"\b(standard|clause|test|marking|amendment|qco|water heater|helmet|toy|"
    r"pressure cooker|which standards?)\b",
    re.IGNORECASE,
)


@dataclass
class Turn:
    question: str
    answer: str = ""
    query_type: str = ""
    standard_ids: List[str] = field(default_factory=list)
    chunk_ids: List[str] = field(default_factory=list)
    answerable: bool = True
    created_at: float = field(default_factory=time.time)


@dataclass
class ConversationState:
    id: str
    selected_product_id: Optional[str] = None
    selected_standard_ids: List[str] = field(default_factory=list)
    last_retrieved_chunk_ids: List[str] = field(default_factory=list)
    turns: List[Turn] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    # -- rolling summary -------------------------------------------------
    @property
    def summary(self) -> str:
        """A few lines of context, not the transcript."""
        if not self.turns:
            return ""
        recent = self.turns[-3:]
        lines = []
        for turn in recent:
            lines.append(f"Q: {truncate(turn.question, 160)}")
            if turn.answer:
                lines.append(f"A: {truncate(turn.answer, 240)}")
        return "\n".join(lines)

    @property
    def last_turn(self) -> Optional[Turn]:
        return self.turns[-1] if self.turns else None

    def record(self, turn: Turn) -> None:
        self.turns.append(turn)
        if len(self.turns) > MAX_TURNS:
            self.turns = self.turns[-MAX_TURNS:]
        if turn.standard_ids:
            self.selected_standard_ids = list(turn.standard_ids)
        if turn.chunk_ids:
            self.last_retrieved_chunk_ids = list(turn.chunk_ids)
        self.updated_at = time.time()

    def as_dict(self) -> Dict[str, object]:
        return {
            "conversation_id": self.id,
            "selected_product_id": self.selected_product_id,
            "selected_standard_ids": self.selected_standard_ids,
            "last_retrieved_chunk_ids": self.last_retrieved_chunk_ids,
            "turns": len(self.turns),
        }


def is_follow_up(question: str) -> bool:
    """True when the question cannot stand on its own.

    Deliberately conservative: if the user named a subject, treat it as a new
    question even if it starts with "and". Carrying stale scope into a question
    the user meant freshly is worse than losing a little context.
    """
    text = (question or "").strip()
    if not text:
        return False
    if extract_is_numbers(text):
        return False  # names a standard outright
    if _SELF_CONTAINED.search(text) and not _FOLLOW_UP_OPENERS.match(text):
        return False
    if _FOLLOW_UP_OPENERS.match(text):
        return True
    # Short question leaning on a pronoun: "why is that needed?"
    return bool(_DANGLING_REFERENCE.search(text)) and len(text.split()) <= 14


class ConversationStore:
    """In-memory, TTL'd. Intentionally not a database - this is scrollback."""

    def __init__(self) -> None:
        self._items: Dict[str, ConversationState] = {}
        self._lock = threading.Lock()

    def _evict(self) -> None:
        now = time.time()
        stale = [k for k, v in self._items.items() if now - v.updated_at > TTL_SECONDS]
        for key in stale:
            self._items.pop(key, None)
        if len(self._items) > MAX_CONVERSATIONS:
            for key, _ in sorted(self._items.items(), key=lambda kv: kv[1].updated_at)[
                : len(self._items) - MAX_CONVERSATIONS
            ]:
                self._items.pop(key, None)

    def get(self, conversation_id: Optional[str]) -> Optional[ConversationState]:
        if not conversation_id:
            return None
        with self._lock:
            self._evict()
            return self._items.get(conversation_id)

    def get_or_create(
        self, conversation_id: Optional[str], *, product_id: Optional[str] = None
    ) -> ConversationState:
        with self._lock:
            self._evict()
            if conversation_id and conversation_id in self._items:
                state = self._items[conversation_id]
                if product_id:
                    state.selected_product_id = product_id
                return state
            new_id = conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
            state = ConversationState(id=new_id, selected_product_id=product_id)
            self._items[new_id] = state
            return state

    def reset(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:  # pragma: no cover - diagnostics
        return len(self._items)


_store = ConversationStore()


def get_conversation_store() -> ConversationStore:
    return _store
