"""Recap Studio: one click turns the verified match facts into broadcaster/studio/fan-ready formats.

Formats: social post, push notification, broadcast lower-third, newsletter, two-host podcast (rendered to MP3 with
two Azure neural voices). Every text goes through the same verification as insights (numbers traceable to the facts,
cited minutes must be real event minutes) and can be produced in any of the 14 languages (translated after
verification, numbers re-checked).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

from app.agents.evidence import verify_output
from app.core.config import BACKEND_DIR
from app.core.logging import get_logger
from app.data.teams import team_name
from app.services.story import bad_minutes, valid_minutes

log = get_logger("recap")
AUDIO_DIR = BACKEND_DIR / "data_cache" / "recaps"
HOSTS = {"A": ("en-US-AndrewMultilingualNeural", "casual_commentator"), "B": ("en-US-AvaMultilingualNeural", "tactical_analyst")}

PROMPT = """You are the content desk of a football studio. Using ONLY the FACTS JSON, write ready-to-publish recap formats.
Never invent numbers, players, minutes or events; goal minutes and scorers come only from FACTS.goals. If FACTS.status is
"in_progress", write it as a live update (never say the match ended). All clubs and players are fictional (synthetic data).
Return JSON:
{"headline": "≤ 10 words",
 "social_post": "≤ 260 characters, energetic, 2 hashtags made from the club names",
 "push_notification": "≤ 100 characters",
 "lower_third": {"title": "≤ 38 characters", "subtitle": "≤ 70 characters"},
 "newsletter": "3 short paragraphs: what happened, the tactical story, the standout player",
 "podcast": [{"host": "A", "line": "..."}, {"host": "B", "line": "..."}]  // 8–10 lines, A = energetic presenter, B = tactical analyst
}"""


class RecapService:
    def __init__(self, llm, speech, translator) -> None:
        self.llm, self.speech, self.translator = llm, speech, translator

    def _fallback(self, f: dict) -> dict:
        goals = ", ".join(f"{g['scorer']} {g['clock'].split(':')[0]}'" for g in f["goals"]) or "no goals yet"
        potm = (f.get("player_of_the_match") or {}).get("name", "")
        h = f["score"]
        return {"headline": h, "social_post": f"{h}. Goals: {goals}.", "push_notification": h,
                "lower_third": {"title": h[:38], "subtitle": f"Goals: {goals}"[:70]},
                "newsletter": f"{h}.\n\nGoals: {goals}.\n\nStandout player: {potm}.",
                "podcast": [{"host": "A", "line": f"Welcome back. {h}."}, {"host": "B", "line": f"The goals: {goals}."},
                            {"host": "A", "line": f"Player of the match for our model: {potm}."}]}

    def _texts(self, r: dict) -> dict:
        t = {"headline": r.get("headline", ""), "social": r.get("social_post", ""), "push": r.get("push_notification", ""),
             "lt_title": (r.get("lower_third") or {}).get("title", ""), "lt_sub": (r.get("lower_third") or {}).get("subtitle", ""),
             "newsletter": r.get("newsletter", "")}
        for i, ln in enumerate(r.get("podcast") or []):
            t[f"pod_{i}"] = ln.get("line", "") if isinstance(ln, dict) else str(ln)
        return t

    async def build(self, rt, story_facts: dict, language: str = "en", audio: bool = True) -> dict:
        f = story_facts
        res = await self.llm.complete_json(system=PROMPT, user="FACTS:\n" + json.dumps(f, default=str)[:11000], tier="large",
                                           fallback=lambda: self._fallback(f), max_tokens=1400, temperature=0.5, interactive=True)
        r = res.data if isinstance(res.data, dict) else self._fallback(f)
        r.setdefault("lower_third", {})
        r["podcast"] = [x for x in (r.get("podcast") or []) if isinstance(x, dict) and x.get("line")][:12]
        # verification: numbers traceable + cited minutes must be real event minutes
        texts = self._texts(r)
        check = verify_output({"explanations": texts}, {"facts": f, "valid_event_ids": []})
        vm = valid_minutes(f)
        safe = self._fallback(f)
        issues = list(check["issues"])
        for k, v in texts.items():
            if bad_minutes(v, vm):
                issues.append(f"{k}: cited a minute that is not an event minute")
        bad_fields = {i.split(":")[0] for i in issues}
        if bad_fields:
            for k in bad_fields:
                if k == "social":
                    r["social_post"] = safe["social_post"]
                elif k == "push":
                    r["push_notification"] = safe["push_notification"]
                elif k in ("lt_title", "lt_sub"):
                    r["lower_third"] = safe["lower_third"]
                elif k == "headline":
                    r["headline"] = safe["headline"]
                elif k == "newsletter":
                    r["newsletter"] = safe["newsletter"]
                elif k.startswith("pod_"):
                    r["podcast"] = safe["podcast"]
        # deterministic broadcast stats (never generated)
        tot = f.get("totals", {})
        def fmt(key, v):
            return f"{round(v * 100)}%" if key in ("possession", "field_tilt") and isinstance(v, (int, float)) and v <= 1 else v
        r["key_stats"] = [{"label": lab, **{t: fmt(key, v.get(key)) for t, v in tot.items()}} for lab, key in
                          (("xG", "xg"), ("Shots", "shots"), ("Possession", "possession"), ("Field tilt", "field_tilt"))]
        r["score"] = f["score"]
        r["status"] = f["status"]
        r["verification"] = {"passed": not issues, "issues": issues[:6], "corrected_fields": sorted(bad_fields)}
        r["model"] = res.model
        if language and language != "en":
            tx = await self.translator.translate(self._texts(r), language, [p.get("name") for p in [f.get("player_of_the_match") or {}] if p.get("name")])
            t = tx["fields"]
            r.update({"headline": t["headline"], "social_post": t["social"], "push_notification": t["push"], "newsletter": t["newsletter"],
                      "lower_third": {"title": t["lt_title"], "subtitle": t["lt_sub"]}})
            for i, ln in enumerate(r["podcast"]):
                ln["line"] = t.get(f"pod_{i}", ln["line"])
            r["translation"] = {"language": tx["lang"], "verified": tx["verified"]}
        r["language"] = language
        # audio=False returns the verified text at once; the client then voices it via podcast() (TTS takes ~10 s)
        r["podcast_url"] = await self._podcast(r["podcast"], language) if audio else None
        r["podcast_pending"] = not audio and self.speech.enabled and bool(r["podcast"])
        return r

    async def podcast(self, lines: list[dict], language: str) -> str | None:
        clean = [{"host": "B" if ln.get("host") == "B" else "A", "line": str(ln.get("line", ""))[:400]}
                 for ln in lines[:12] if isinstance(ln, dict) and ln.get("line")]
        return await self._podcast(clean, language)

    async def _podcast(self, lines: list[dict], language: str) -> str | None:
        if not self.speech.enabled or not lines:
            return None
        key = hashlib.sha1(json.dumps([language, lines], ensure_ascii=False).encode()).hexdigest()[:16]
        out = AUDIO_DIR / f"{key}.mp3"
        if out.exists():
            return f"/api/recaps/{key}.mp3"
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        clips = []
        for i, ln in enumerate(lines):
            voice, persona_name = HOSTS.get(ln.get("host", "A"), HOSTS["A"])
            audio = await self.speech.synthesize(ln["line"], persona_name, language,
                                                 voice_override=voice if language == "en" else None)
            if audio:
                p = AUDIO_DIR / f"{key}_{i:02d}.mp3"
                p.write_bytes(audio)
                clips.append(p)
        if not clips:
            return None
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        inputs, parts = [], []
        for i, c in enumerate(clips):
            inputs += ["-i", str(c)]
            parts.append(f"[{i}:a]aresample=24000,apad=pad_dur=0.35[p{i}]")
        filt = ";".join(parts) + ";" + "".join(f"[p{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=0:a=1,loudnorm=I=-16:TP=-1.5[out]"
        await asyncio.to_thread(subprocess.run, [ff, "-y", "-loglevel", "error", *inputs, "-filter_complex", filt, "-map", "[out]",
                                                 "-c:a", "libmp3lame", "-b:a", "128k", str(out)], check=True)
        for c in clips:
            c.unlink(missing_ok=True)
        return f"/api/recaps/{key}.mp3"
