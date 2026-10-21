"""Supported commentary languages: Azure neural voice + speech-recognition locale per language."""
from __future__ import annotations

LANGUAGES: dict[str, dict] = {
    "en": {"name": "English", "native": "English", "locale": "en-US", "voice": None, "rtl": False},
    "es": {"name": "Spanish", "native": "Español", "locale": "es-ES", "voice": "es-ES-ElviraNeural", "rtl": False},
    "fr": {"name": "French", "native": "Français", "locale": "fr-FR", "voice": "fr-FR-DeniseNeural", "rtl": False},
    "pt": {"name": "Portuguese", "native": "Português", "locale": "pt-BR", "voice": "pt-BR-FranciscaNeural", "rtl": False},
    "de": {"name": "German", "native": "Deutsch", "locale": "de-DE", "voice": "de-DE-KatjaNeural", "rtl": False},
    "it": {"name": "Italian", "native": "Italiano", "locale": "it-IT", "voice": "it-IT-ElsaNeural", "rtl": False},
    "nl": {"name": "Dutch", "native": "Nederlands", "locale": "nl-NL", "voice": "nl-NL-ColetteNeural", "rtl": False},
    "ar": {"name": "Arabic", "native": "العربية", "locale": "ar-SA", "voice": "ar-SA-ZariyahNeural", "rtl": True},
    "ur": {"name": "Urdu", "native": "اردو", "locale": "ur-PK", "voice": "ur-PK-UzmaNeural", "rtl": True},
    "hi": {"name": "Hindi", "native": "हिन्दी", "locale": "hi-IN", "voice": "hi-IN-SwaraNeural", "rtl": False},
    "tr": {"name": "Turkish", "native": "Türkçe", "locale": "tr-TR", "voice": "tr-TR-EmelNeural", "rtl": False},
    "ja": {"name": "Japanese", "native": "日本語", "locale": "ja-JP", "voice": "ja-JP-NanamiNeural", "rtl": False},
    "ko": {"name": "Korean", "native": "한국어", "locale": "ko-KR", "voice": "ko-KR-SunHiNeural", "rtl": False},
    "zh": {"name": "Chinese", "native": "中文", "locale": "zh-CN", "voice": "zh-CN-XiaoxiaoNeural", "rtl": False},
}


def language(code: str | None) -> dict:
    return LANGUAGES.get((code or "en").split("-")[0].lower(), LANGUAGES["en"])
