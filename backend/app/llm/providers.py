"""HTTP implementations for the supported LLM providers.

Plain httpx is used instead of vendor SDKs so that adding a provider is a
30-line change and the deployment image stays small.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import httpx

from app.llm.base import LLMMessage, LLMProvider, LLMResult

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-4o-mini"
    base_url = "https://api.openai.com/v1/chat/completions"

    def generate(self, system, messages, *, json_mode=False, temperature=0.1, max_tokens=1600):
        payload: Dict[str, Any] = {
            "model": self.model or self.default_model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            resp = httpx.post(
                self.base_url,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return LLMResult(
                text=data["choices"][0]["message"]["content"],
                provider=self.name,
                model=payload["model"],
                raw=data,
            )
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("OpenAI call failed: %s", exc)
            return LLMResult("", self.name, payload["model"], error=str(exc))


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-sonnet-5"
    base_url = "https://api.anthropic.com/v1/messages"

    def generate(self, system, messages, *, json_mode=False, temperature=0.1, max_tokens=1600):
        model = self.model or self.default_model
        content = [{"role": m.role, "content": m.content} for m in messages]
        if json_mode:
            system = system + "\n\nRespond with a single valid JSON object and nothing else."
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": content,
        }
        try:
            resp = httpx.post(
                self.base_url,
                json=payload,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(
                block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
            )
            return LLMResult(text=text, provider=self.name, model=model, raw=data)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("Anthropic call failed: %s", exc)
            return LLMResult("", self.name, model, error=str(exc))


class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-1.5-flash"

    def generate(self, system, messages, *, json_mode=False, temperature=0.1, max_tokens=1600):
        model = self.model or self.default_model
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        )
        parts: List[Dict[str, Any]] = []
        for m in messages:
            parts.append({"role": "user" if m.role != "assistant" else "model",
                          "parts": [{"text": m.content}]})
        generation_config: Dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": parts,
            "generationConfig": generation_config,
        }
        try:
            resp = httpx.post(
                url,
                json=payload,
                headers={"x-goog-api-key": self.api_key},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(
                p.get("text", "")
                for p in data["candidates"][0]["content"]["parts"]
            )
            return LLMResult(text=text, provider=self.name, model=model, raw=data)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("Gemini call failed: %s", exc)
            return LLMResult("", self.name, model, error=str(exc))


class NullProvider(LLMProvider):
    """Used when no API key is configured. Never fabricates content."""

    name = "none"

    def __init__(self) -> None:
        super().__init__("", "", 1)

    @property
    def available(self) -> bool:
        return False

    def generate(self, system, messages, *, json_mode=False, temperature=0.1, max_tokens=1600):
        return LLMResult("", self.name, "", error="no_llm_provider_configured")


PROVIDERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}


def extract_json(text: str) -> Any:
    """Best-effort JSON recovery from a model response."""
    if not text:
        raise ValueError("empty response")
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("response did not contain valid JSON")
