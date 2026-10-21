"""Verified translation of already-verified commentary.

Translation happens AFTER fact verification, so facts are fixed before any language is produced. The output is
checked again: the multiset of numbers in every translated field must equal the English source (Arabic-Indic and
Devanagari digits and decimal commas are normalised), and player/team names must survive. One retry with
feedback, otherwise the English original is returned with `verified: false`. Results are cached per
(text, language) and shared by every fan using that language.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

from app.services.observability import OBS
from app.voice.languages import language

DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹०१२३४५६७८९０１２３４５６７８９",
                          "0123456789" "0123456789" "0123456789" "0123456789")
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")

SYSTEM = """You translate live football commentary. Translate every JSON field into {lang_name} ({lang_native}).
RULES
- Never add, change or round a number. Decimals, percentages and years must appear exactly, in Western digits 0-9.
  Small whole numbers may be written as words or folded into a standard phrase (e.g. "Round of 16" → "octavos de final").
- Keep player names exactly in their original Latin spelling. Team / country names may use the standard local form.
- Keep football meaning precise (PPDA, xG may stay as abbreviations). Natural, broadcast-quality phrasing.
- Do not add or remove facts. Return JSON with exactly the same keys."""


def numbers(text: str) -> Counter:
    t = (text or "").translate(DIGIT_MAP)
    return Counter(n.replace(",", ".") for n in NUM_RE.findall(t))


class Translator:
    """`names` should contain PLAYER names only — they must survive verbatim; team names may be localised."""
    def __init__(self, llm, kv) -> None:
        self.llm, self.kv = llm, kv

    def _check(self, src: dict, out: dict, names: list[str]) -> list[str]:
        issues = []
        for k, v in src.items():
            t = out.get(k)
            if not isinstance(t, str) or not t.strip():
                issues.append(f"{k}: missing translation")
                continue
            src_n, out_n = numbers(v), numbers(t)
            added = out_n - src_n
            must_keep = Counter({n: c for n, c in src_n.items() if "." in n or float(n) >= 100})
            missing = must_keep - out_n
            if added or missing:
                issues.append(f"{k}: numbers changed (added {sorted(added.elements())}, missing {sorted(missing.elements())})")
            for n in names:
                if n in v and n not in t:
                    issues.append(f"{k}: name '{n}' altered")
        return issues

    async def translate(self, fields: dict[str, str], lang: str, names: list[str] | None = None,
                        interactive: bool = True) -> dict:
        lang_meta = language(lang)
        src = {k: v for k, v in fields.items() if isinstance(v, str) and v.strip()}
        if lang_meta["locale"].startswith("en") or not src:
            return {"fields": fields, "lang": "en", "verified": True, "cached": False}
        names = [n for n in (names or []) if any(n in v for v in src.values())]
        key = "tr:" + hashlib.sha1(f"{lang}|{json.dumps(src, sort_keys=True)}".encode()).hexdigest()[:28]
        hit = await self.kv.get_json(key)
        if hit:
            OBS.incr("translation_cache_hits")
            return {**hit, "cached": True}
        system = SYSTEM.format(lang_name=lang_meta["name"], lang_native=lang_meta["native"])
        user = json.dumps(src, ensure_ascii=False)
        issues: list[str] = []
        result = None
        for attempt in range(2):
            prompt = user if not issues else user + "\n\nFIX THESE PROBLEMS FROM YOUR LAST ATTEMPT:\n- " + "\n- ".join(issues)
            res = await self.llm.complete_json(system=system, user=prompt, tier="small", fallback=lambda: {},
                                               max_tokens=900, temperature=0.2, interactive=interactive)
            if res.fallback:
                break
            issues = self._check(src, res.data, names)
            if not issues:
                result = {"fields": {**fields, **{k: res.data[k] for k in src}}, "lang": lang, "verified": True,
                          "model": res.model}
                break
            OBS.incr("translation_retries")
        if result is None:
            OBS.incr("translation_rejected")
            return {"fields": fields, "lang": "en", "verified": False, "issues": issues[:4], "cached": False}
        OBS.incr("translations")
        await self.kv.set_json(key, result, 7 * 24 * 3600)
        return {**result, "cached": False}
