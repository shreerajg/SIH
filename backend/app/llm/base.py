"""Provider-agnostic LLM interface."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    raw: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text)


class LLMProvider(abc.ABC):
    """Minimal surface every provider must implement."""

    name: str = "abstract"

    def __init__(self, api_key: str, model: str, timeout: int = 60) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @abc.abstractmethod
    def generate(
        self,
        system: str,
        messages: List[LLMMessage],
        *,
        json_mode: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 1600,
    ) -> LLMResult:
        raise NotImplementedError


class LLMUnavailable(RuntimeError):
    """Raised when no provider is configured and a caller demanded one."""
