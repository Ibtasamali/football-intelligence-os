"""Embedding adapters.

AzureEmbedder uses an Azure OpenAI embedding deployment when configured. LocalEmbedder is a
football-aware hashed n-gram embedder (signed feature hashing over normalised unigrams + bigrams):
fast, deterministic, no network — good enough for a curated knowledge base and fully replaceable.
"""
from __future__ import annotations

import hashlib
import math
import re

import numpy as np

DIM = 512

# Normalise football vocabulary so "pressing", "pressure" and "press" land on the same feature.
CANON = {
    "pressing": "press", "pressure": "press", "pressures": "press", "pressed": "press", "gegenpressing": "counterpress",
    "counterpressing": "counterpress", "counter": "transition", "counters": "transition", "counterattack": "transition",
    "counterattacks": "transition", "break": "transition", "breaks": "transition", "transitions": "transition",
    "wing": "flank", "wings": "flank", "flanks": "flank", "wide": "flank", "side": "flank",
    "fullback": "fullback", "full-back": "fullback", "rightback": "fullback", "right-back": "fullback",
    "leftback": "fullback", "left-back": "fullback", "overlapping": "overlap", "overlaps": "overlap",
    "overloads": "overload", "overloaded": "overload", "overloading": "overload",
    "crosses": "cross", "crossing": "cross", "goals": "goal", "scored": "goal", "scores": "goal",
    "deep": "deep", "low": "deep", "block": "block", "defending": "defend", "defensive": "defend",
    "substitute": "substitution", "sub": "substitution", "subs": "substitution", "substitutions": "substitution",
    "turnover": "turnover", "turnovers": "turnover", "recoveries": "recovery", "recovered": "recovery",
    "midfield": "midfield", "central": "centre", "center": "centre", "matches": "match", "games": "match", "game": "match",
}
STOP = {"the", "a", "an", "of", "to", "in", "and", "or", "is", "was", "were", "this", "that", "with", "for", "on",
        "at", "by", "it", "as", "be", "their", "they", "them", "from", "after", "into", "over", "than", "what", "why"}


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-zà-ÿ0-9\-']+", text.lower())
    out = []
    for t in toks:
        t = CANON.get(t, t)
        if t in STOP or len(t) < 2:
            continue
        if t.endswith("s") and len(t) > 4 and t[:-1] in CANON.values():
            t = t[:-1]
        out.append(t)
    return out


def _h(feature: str) -> tuple[int, float]:
    d = hashlib.blake2b(feature.encode(), digest_size=8).digest()
    idx = int.from_bytes(d[:4], "little") % DIM
    sign = 1.0 if d[4] & 1 else -1.0
    return idx, sign


class LocalEmbedder:
    name = "local-hash-ngram-512"
    dim = DIM

    def embed_one(self, text: str) -> list[float]:
        toks = tokenize(text)
        vec = np.zeros(DIM, dtype=np.float32)
        feats: dict[str, float] = {}
        for t in toks:
            feats[t] = feats.get(t, 0) + 1.0
        for a, b in zip(toks, toks[1:]):
            feats[f"{a}_{b}"] = feats.get(f"{a}_{b}", 0) + 0.7
        for f, c in feats.items():
            i, s = _h(f)
            vec[i] += s * (1 + math.log(c))
        n = float(np.linalg.norm(vec))
        return (vec / n).tolist() if n else vec.tolist()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


class AzureEmbedder:
    def __init__(self, client, deployment: str, dim: int = 1536) -> None:
        self.client, self.deployment, self.dim = client, deployment, dim
        self.name = f"azure:{deployment}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self.client.embeddings.create(model=self.deployment, input=texts)
        return [d.embedding for d in resp.data]


class CachedEmbedder:
    """Embedding cache: identical text is embedded once (shared across users, matches, agents)."""

    def __init__(self, inner, kv=None) -> None:
        self.inner, self.kv = inner, kv
        self.name, self.dim = inner.name, inner.dim
        self._local: dict[str, list[float]] = {}

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float] | None] = []
        missing = []
        for i, t in enumerate(texts):
            k = hashlib.sha1(f"{self.name}|{t}".encode()).hexdigest()
            v = self._local.get(k)
            out.append(v)
            if v is None:
                missing.append((i, t, k))
        if missing:
            vecs = await self.inner.embed([t for _, t, _ in missing])
            for (i, _, k), v in zip(missing, vecs):
                self._local[k] = v
                out[i] = v
        return out  # type: ignore[return-value]


def build_embedder(settings, kv=None):
    if settings.llm_enabled and settings.azure_openai_embedding_deployment:
        from openai import AsyncAzureOpenAI
        client = AsyncAzureOpenAI(azure_endpoint=settings.azure_openai_endpoint, api_key=settings.azure_openai_api_key,
                                  api_version=settings.azure_openai_api_version)
        return CachedEmbedder(AzureEmbedder(client, settings.azure_openai_embedding_deployment), kv)
    return CachedEmbedder(LocalEmbedder(), kv)
