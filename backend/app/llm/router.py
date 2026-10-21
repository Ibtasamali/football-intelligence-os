"""Model router: picks the cheapest model tier that can do the job, caches responses, meters tokens.

Tiers
  none  → deterministic code only (most events)
  small → Azure OpenAI small deployment (e.g. gpt-4.1-mini) for notable events / Q&A
  large → Azure OpenAI large deployment for major turning points and match stories

Every call supplies a `fallback` that builds the same JSON shape from evidence alone. It runs when Azure
is not configured, when the call fails or times out, or in tests — so the pipeline never blocks on an
LLM and never needs one to produce grounded output.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.observability import OBS
from app.services.tracing import span

log = get_logger("llm")


@dataclass
class LLMResult:
    data: dict
    model: str
    tokens: int
    latency_ms: float
    cached: bool = False
    fallback: bool = False


class ModelRouter:
    def __init__(self, settings: Settings, cache=None) -> None:
        self.settings = settings
        self.cache = cache  # JsonKV
        self.client = None
        if settings.llm_enabled:
            from openai import AsyncAzureOpenAI
            self.client = AsyncAzureOpenAI(azure_endpoint=settings.azure_openai_endpoint,
                                           api_key=settings.azure_openai_api_key,
                                           api_version=settings.azure_openai_api_version,
                                           timeout=settings.llm_timeout_seconds, max_retries=4)
        self._sem = asyncio.Semaphore(2)
        self._interactive = asyncio.Semaphore(4)  # fan questions never queue behind live analysis

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def deployment(self, tier: str) -> str:
        return self.settings.large_deployment if tier == "large" else self.settings.azure_openai_deployment

    async def complete_json(self, *, system: str, user: str, tier: str, fallback: Callable[[], dict],
                            max_tokens: int = 700, temperature: float = 0.4, cache_ttl: int = 7 * 24 * 3600,
                            interactive: bool = False) -> LLMResult:
        if tier == "none" or not self.enabled:
            t0 = time.perf_counter()
            data = fallback()
            return LLMResult(data, "local-reasoner", 0, (time.perf_counter() - t0) * 1000, fallback=True)

        model = self.deployment(tier)
        key = "llm:" + hashlib.sha256(f"{model}|{system}|{user}|{temperature}".encode()).hexdigest()[:40]
        if self.cache:
            hit = await self.cache.get_json(key)
            if hit:
                OBS.record_llm(model, hit.get("_tokens", 0), 0, cached=True)
                return LLMResult(hit["data"], model, 0, 0.0, cached=True)

        t0 = time.perf_counter()
        try:
            with span("llm.complete", model_name=model, model_tier=tier, interactive=interactive,
                      gen_ai_operation_name="chat", gen_ai_request_model=model) as sp:
                async with (self._interactive if interactive else self._sem):
                    resp = await self.client.chat.completions.create(
                        model=model, temperature=temperature, max_tokens=max_tokens,
                        response_format={"type": "json_object"},
                        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
                if resp.usage:
                    sp.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
                    sp.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
            latency = (time.perf_counter() - t0) * 1000
            data = json.loads(resp.choices[0].message.content or "{}")
            tokens = resp.usage.total_tokens if resp.usage else 0
            OBS.record_llm(model, tokens, latency, cached=False)
            if resp.usage:
                OBS.incr("tokens_prompt", resp.usage.prompt_tokens)
                OBS.incr("tokens_completion", resp.usage.completion_tokens)
            if self.cache:
                await self.cache.set_json(key, {"data": data, "_tokens": tokens}, cache_ttl)
            return LLMResult(data, model, tokens, latency)
        except Exception as exc:  # noqa: BLE001
            OBS.incr("llm_failures")
            log.warning("llm_failed_using_fallback", error=str(exc)[:300], model=model)
            data = fallback()
            return LLMResult(data, "local-reasoner", 0, (time.perf_counter() - t0) * 1000, fallback=True)
