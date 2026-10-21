from app.voice.intent import detect_intent
from app.voice.personas import PERSONAS
from app.voice.speech import SpeechService


def test_intents():
    assert detect_intent("What just happened?").name == "WHAT_HAPPENED"
    assert detect_intent("Explain this like I'm a beginner").name == "EXPLAIN_SIMPLER"
    assert detect_intent("Give me an analyst-level explanation").name == "EXPLAIN_EXPERT"
    assert detect_intent("Compare this attack with the previous one").name == "COMPARE"
    assert detect_intent("Who is the best player?").name == "BEST_PLAYER"
    assert detect_intent("Why did that goal happen?").name == "WHY"


def test_entity_extraction():
    i = detect_intent("Why is Mensah getting forward so much for Thames Athletic?")
    assert "tha_2" in i.players and "tha" in i.teams


def test_personas_cover_brief():
    assert {"casual_commentator", "tactical_analyst", "coach", "kids", "expert_analyst"} <= set(PERSONAS)


async def test_tts_disabled_returns_none():
    from app.core.config import Settings
    s = SpeechService(Settings(_env_file=None, azure_speech_key=""))
    assert await s.synthesize("hello") is None
    ssml, voice = s.ssml("a < b", "kids")
    assert "&lt;" in ssml and voice
