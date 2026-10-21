"""Azure AI Document Intelligence adapter: turns scouting / opposition reports (PDF, images) into text
that is chunked and indexed into the RAG knowledge base."""
from __future__ import annotations

import asyncio
import re

import httpx

from app.core.config import Settings


class DocumentIntelligence:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    @property
    def enabled(self) -> bool:
        return self.s.doc_intel_enabled

    async def extract_text(self, data: bytes, content_type: str) -> str:
        if not self.enabled:
            raise RuntimeError("Azure Document Intelligence is not configured")
        base = self.s.azure_doc_intel_endpoint.rstrip("/")
        url = f"{base}/documentintelligence/documentModels/prebuilt-read:analyze?api-version=2024-11-30"
        headers = {"Ocp-Apim-Subscription-Key": self.s.azure_doc_intel_key, "Content-Type": content_type}
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, content=data, headers=headers)
            r.raise_for_status()
            op = r.headers["Operation-Location"]
            for _ in range(60):
                await asyncio.sleep(1.0)
                p = await client.get(op, headers={"Ocp-Apim-Subscription-Key": self.s.azure_doc_intel_key})
                p.raise_for_status()
                body = p.json()
                if body.get("status") == "succeeded":
                    return body["analyzeResult"].get("content", "")
                if body.get("status") == "failed":
                    raise RuntimeError(f"Document analysis failed: {body.get('error')}")
        raise TimeoutError("Document analysis timed out")


def chunk(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    out, i = [], 0
    while i < len(text):
        piece = text[i:i + size]
        if i + size < len(text):
            cut = piece.rfind(". ")
            if cut > size * 0.5:
                piece = piece[:cut + 1]
        out.append(piece.strip())
        i += max(1, len(piece) - overlap)
    return [c for c in out if len(c) > 40]
