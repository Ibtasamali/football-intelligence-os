"""Voice personalities: how each persona speaks (prompt style) and sounds (Azure neural voice + SSML prosody)."""
from __future__ import annotations

PERSONAS = {
    "casual_commentator": {
        "label": "Casual Commentator", "level": "intermediate",
        "voice": "en-US-AndrewMultilingualNeural", "style": None, "rate": "+6%", "pitch": "+0%",
        "prompt": "Energetic TV commentator. Vivid, warm, short sentences, no jargon beyond the basics.",
    },
    "tactical_analyst": {
        "label": "Tactical Analyst", "level": "advanced",
        "voice": "en-US-AvaMultilingualNeural", "style": None, "rate": "+0%", "pitch": "+0%",
        "prompt": "Calm studio analyst. Explain cause and effect, name the tactical mechanism, cite one or two numbers.",
    },
    "coach": {
        "label": "Coach", "level": "advanced",
        "voice": "en-US-BrianMultilingualNeural", "style": None, "rate": "-2%", "pitch": "-2%",
        "prompt": "Head coach in a team meeting. Focus on what the players did, what should be adjusted, and why.",
    },
    "kids": {
        "label": "Kids Mode", "level": "beginner",
        "voice": "en-US-AnaNeural", "style": None, "rate": "-4%", "pitch": "+6%",
        "prompt": "Friendly guide for a 9-year-old. Very simple words, a fun comparison, one idea per sentence.",
    },
    "expert_analyst": {
        "label": "Expert Analyst", "level": "professional",
        "voice": "en-US-AvaMultilingualNeural", "style": None, "rate": "+2%", "pitch": "-2%",
        "prompt": "Elite performance analyst. Precise terminology (PPDA, rest defence, half-spaces), quantified evidence.",
    },
}

LEVEL_FOR_PERSONA = {k: v["level"] for k, v in PERSONAS.items()}


def persona(name: str | None) -> dict:
    return PERSONAS.get(name or "", PERSONAS["casual_commentator"])
