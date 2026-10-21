from app.agents.evidence import verify_output
from app.agents.reasoning_agents import normalize_narrative

EVIDENCE = {"valid_event_ids": ["ev1", "ev2"], "metrics": {"analysis.pressing_analysis.azc.ppda_5min": 3.2},
            "analysis": {"pressing": {"ppda": 3.2, "share": 0.58}}, "documents": [{"title": "Matchday 7 — A 3–2 B"}],
            "match": {"clock": "34:50"}}


def ok(text, **kw):
    return {"headline": "h", "explanations": {"professional": text}, "claims": [{"text": text, "event_ids": ["ev1"], **kw}]}


def test_grounded_output_passes():
    r = verify_output(ok("PPDA dropped to 3.2 and 58% of attacks went right, like Matchday 7."), EVIDENCE)
    assert r["passed"], r["issues"]


def test_invented_number_rejected():
    r = verify_output(ok("They completed 87 passes."), EVIDENCE)
    assert not r["passed"] and any("87" in i for i in r["issues"])


def test_unretrieved_match_rejected():
    r = verify_output(ok("Just like Matchday 30."), EVIDENCE)
    assert any("Matchday 30" in i for i in r["issues"])


def test_unknown_event_rejected():
    r = verify_output({"claims": [{"text": "x", "event_ids": ["ev999"]}]}, EVIDENCE)
    assert r["unverified_claims"]


def test_prediction_as_certainty_rejected():
    r = verify_output(ok("Azure City will score next."), EVIDENCE)
    assert any("certainty" in i for i in r["issues"])


def test_metric_short_name_accepted():
    r = verify_output(ok("PPDA 3.2", metric_refs=["ppda_5min"]), EVIDENCE)
    assert r["passed"], r["issues"]


def test_malformed_llm_output_normalised():
    n = normalize_narrative({"claims": ["plain string", {"text": "t", "event_ids": "ev1", "metric_refs": None}, {"x": 1}],
                             "explanations": None, "confidence": "high"})
    assert len(n["claims"]) == 2 and n["claims"][1]["event_ids"] == ["ev1"]
    assert set(n["explanations"]) == {"beginner", "intermediate", "advanced", "professional"}
    verify_output(n, EVIDENCE)  # must not raise


def test_translation_number_rules():
    from app.voice.translate import Translator, numbers
    tr = Translator(None, None)
    src = {"t": "Marcus Hale scored a penalty (xG 0.783) in the Round of 16 of 2022, 59% possession."}
    ok = {"t": "Marcus Hale marcó un penalti (xG 0,783) en octavos de final de 2022, 59% de posesión."}
    assert tr._check(src, ok, ["Marcus Hale"]) == []
    bad = {"t": "Marcus Hale marcó un penalti (xG 0,78) en 2022, 59% de posesión."}
    assert tr._check(src, bad, ["Marcus Hale"])
    renamed = {"t": "Marcos Hale marcó un penalti (xG 0.783) en octavos de 2022, 59%."}
    assert any("name" in i for i in tr._check(src, renamed, ["Marcus Hale"]))
    assert numbers("٢٠٢٢") == numbers("2022")


def test_coordinates_rejected():
    r = verify_output(ok("Novak's pass from (50.02,35.78) failed."), EVIDENCE)
    assert any("coordinates" in i for i in r["issues"])
