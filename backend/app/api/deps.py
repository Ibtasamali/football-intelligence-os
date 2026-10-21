"""Shared API dependencies."""
from __future__ import annotations

from fastapi import HTTPException, Request

from app.services.container import Container


def container(request: Request) -> Container:
    return request.app.state.container


def runtime_or_404(c: Container, match_id: str):
    rt = c.runtimes.get(match_id)
    if not rt:
        raise HTTPException(404, f"Match '{match_id}' is not loaded. POST /api/matches first.")
    return rt
