"""Azure AI Speech adapter (neural TTS over REST, plus short-utterance STT).

The browser falls back to the Web Speech API when Speech is not configured. Synthesised clips are
cached by (voice, text) so a commentary line broadcast to many fans is synthesised once.
"""
from __future__ import annotations

import hashlib
from xml.sax.saxutils import escape

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.observability import OBS
from app.voice.languages import language
from app.voice.personas import persona

log = get_logger("speech")


class SpeechService:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._cache: dict[str, bytes] = {}
        self._client = httpx.AsyncClient(timeout=20)

    @property
    def enabled(self) -> bool:
        return self.s.speech_enabled

    def ssml(self, text: str, persona_name: str | None, lang: str | None = None, voice_override: str | None = None) -> tuple[str, str]:
        p = persona(persona_name)
        lm = language(lang)
        voice = voice_override or lm["voice"] or p["voice"] or self.s.azure_speech_voice
        body = f'<prosody rate="{p["rate"]}" pitch="{p["pitch"]}">{escape(text)}</prosody>'
        ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
                f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{lm["locale"]}"><voice name="{voice}">{body}</voice></speak>')
        return ssml, voice

    async def synthesize(self, text: str, persona_name: str | None = None, lang: str | None = None,
                         voice_override: str | None = None) -> bytes | None:
        if not self.enabled or not text.strip():
            return None
        ssml, voice = self.ssml(text[:1500], persona_name, lang, voice_override)
        key = hashlib.sha1(f"{voice}|{ssml}".encode()).hexdigest()
        if key in self._cache:
            OBS.incr("tts_cache_hits")
            return self._cache[key]
        url = f"https://{self.s.azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1"
        headers = {"Ocp-Apim-Subscription-Key": self.s.azure_speech_key, "Content-Type": "application/ssml+xml",
                   "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3", "User-Agent": "football-intelligence-os"}
        try:
            r = await self._client.post(url, content=ssml.encode(), headers=headers)
            if r.status_code == 400 and voice != self.s.azure_speech_voice:  # voice unavailable in region → default
                ssml = ssml.replace(voice, self.s.azure_speech_voice)
                r = await self._client.post(url, content=ssml.encode(), headers=headers)
            r.raise_for_status()
            OBS.incr("tts_requests")
            if len(self._cache) > 500:
                self._cache.clear()
            self._cache[key] = r.content
            return r.content
        except Exception as exc:  # noqa: BLE001
            log.warning("tts_failed", error=str(exc)[:200])
            OBS.incr("tts_failures")
            return None

    async def transcribe(self, audio: bytes, content_type: str = "audio/wav; codecs=audio/pcm; samplerate=16000") -> str | None:
        if not self.enabled:
            return None
        url = (f"https://{self.s.azure_speech_region}.stt.speech.microsoft.com/speech/recognition/conversation/"
               f"cognitiveservices/v1?language=en-US&format=simple")
        headers = {"Ocp-Apim-Subscription-Key": self.s.azure_speech_key, "Content-Type": content_type}
        try:
            r = await self._client.post(url, content=audio, headers=headers)
            r.raise_for_status()
            OBS.incr("stt_requests")
            return r.json().get("DisplayText")
        except Exception as exc:  # noqa: BLE001
            log.warning("stt_failed", error=str(exc)[:200])
            return None
