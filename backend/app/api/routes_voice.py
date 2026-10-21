"""Voice: question answering, neural TTS, short-utterance STT, personas."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.api.deps import container, runtime_or_404
from app.core.security import Principal, get_principal
from app.schemas.api import TTSRequest, VoiceQueryRequest
from app.voice.languages import LANGUAGES
from app.voice.personas import PERSONAS

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.post("/query")
async def voice_query(req: VoiceQueryRequest, request: Request, c=Depends(container), principal: Principal = Depends(get_principal)):
    runtime_or_404(c, req.match_id)
    if not request.app.state.limiter.allow(f"ask:{principal.tenant_id}:{req.user_id or principal.subject}"):
        raise HTTPException(429, "Too many questions — slow down a little.")
    ins = await c.ask(req.match_id, req.text, user_id=req.user_id, persona=req.persona.value if req.persona else None,
                      level=req.level.value if req.level else None, tenant_id=principal.tenant_id, language=req.language)
    await c.db.insert("voice_sessions", {"user_id": req.user_id, "match_id": req.match_id, "question": req.text,
                                         "answer_id": ins["insight_id"], "created_at": ins["created_at"]})
    return {"answer": ins, "tts_available": c.speech.enabled}


@router.post("/tts")
async def tts(req: TTSRequest, c=Depends(container)):
    audio = await c.speech.synthesize(req.text, req.persona.value if req.persona else None, req.language)
    if audio is None:
        raise HTTPException(503, "Azure Speech unavailable — client should use browser speech synthesis")
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=3600"})


@router.post("/stt")
async def stt(audio: UploadFile = File(...), c=Depends(container)):
    data = await audio.read()
    if len(data) > 5_000_000:
        raise HTTPException(413, "Audio too large")
    text = await c.speech.transcribe(data, audio.content_type or "audio/wav")
    if text is None:
        raise HTTPException(503, "Speech-to-text unavailable")
    return {"text": text}


@router.get("/languages")
async def languages():
    return {"languages": [{"code": k, **{kk: v[kk] for kk in ("name", "native", "locale", "rtl")}} for k, v in LANGUAGES.items()]}


@router.get("/personas")
async def personas(c=Depends(container)):
    return {"personas": [{"id": k, "label": v["label"], "level": v["level"], "voice": v["voice"]} for k, v in PERSONAS.items()],
            "azure_speech": c.speech.enabled}
