"""Verified coach/analyst report generation and PDF rendering."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.agents.evidence import verify_output
from app.core.config import BACKEND_DIR
from app.data.teams import player_name, team_name
from app.services.story import bad_minutes
from app.services.tracing import span

REPORT_DIR = BACKEND_DIR / "data_cache" / "reports"

PROMPT = """You are a professional football performance analyst. Write a concise post-match coach report using ONLY
the EVIDENCE JSON. Do not invent numbers, players, events, causes or minutes. Recommendations must cite an evidence
field or event in their rationale. If status is in_progress, call this an interim report. Return JSON:
{"executive_summary":"3 sentences", "tactical_diagnosis":["4 evidence-based bullets"],
 "player_notes":[{"player":"exact supplied name","note":"one evidence-based sentence"}],
 "recommendations":[{"priority":"high|medium|low","action":"specific coaching action","rationale":"evidence"}],
 "training_plan":[{"theme":"session theme","drill":"specific drill","success_measure":"target expressed against a supplied match value (e.g. 'beat the match figure of 1.06 xG'); never invent new numbers"}]}
Possession values: use totals.<team>.possession_pct (already a percentage). Cite evidence in plain football words
("their high press", "the transition breaks") and never write JSON field names, pattern codes or ids."""


class CoachReportService:
    def __init__(self, llm) -> None:
        self.llm = llm

    def evidence(self, rt) -> dict:
        eng = rt.engine
        h, a = eng.home, eng.away
        story = rt.match.status == "finished" or any(e.type.value == "FULL_TIME" for e in eng.events[-3:])
        facts = rt.match.notes.get("attribution", "synthetic, football-realistic demo data")
        influence = eng.player_influence(top=8)
        return {
            "match_id": rt.match_id, "status": "full_time" if story else "in_progress",
            "clock": eng.events[-1].clock if eng.events else "00:00", "data_source": facts,
            "score": {team_name(h): eng.score[h], team_name(a): eng.score[a]},
            "teams": [team_name(h), team_name(a)],
            "totals": {team_name(t): {**d, "possession_pct": round(d.get("possession", 0) * 100, 1) if d.get("possession", 0) <= 1 else d.get("possession")}
                       for t, d in eng.totals().items()},
            "active_patterns": rt.patterns.active_list(),
            "pattern_history": [{**p, "team": team_name(p.get("team_id"))} for p in rt.patterns.history[-16:]],
            "player_influence": influence,
            "substitutions": [{**s, "team": team_name(s["team_id"]), "on_name": player_name(s["on"]),
                               "off_name": player_name(s["off"])} for s in eng.substitutions],
            "goals": [{"clock": e.clock, "team": team_name(e.team_id), "scorer": player_name(e.player_id),
                       "assist": player_name(e.related_player_id) if e.related_player_id else None,
                       "xg": e.meta.get("xg"), "event_id": e.event_id}
                      for e in eng.events if e.type.value == "GOAL"],
            "verified_insights": [{"clock": f"{i.minute:02d}:{i.second:02d}", "headline": i.headline,
                                    "category": i.category, "claims": [c.text for c in i.claims if c.verified],
                                    "event_id": i.event_id, "confidence": i.provenance.confidence}
                                   for i in rt.insights[-12:]],
        }

    def fallback(self, e: dict) -> dict:
        teams = e["teams"]
        totals = e["totals"]
        h, a = teams
        ht, at = totals[h], totals[a]
        patterns = [p for p in e["pattern_history"] if p.get("event") == "start"]
        top = e["player_influence"][:4]
        score = f"{h} {e['score'][h]}-{e['score'][a]} {a}"
        status = "Interim" if e["status"] == "in_progress" else "Full-time"
        diagnosis = [
            f"{h}: {ht.get('shots', 0)} shots, {ht.get('xg', 0)} xG, {ht.get('possession_pct', 0)}% possession.",
            f"{a}: {at.get('shots', 0)} shots, {at.get('xg', 0)} xG, {at.get('possession_pct', 0)}% possession.",
        ]
        diagnosis += [f"{p.get('minute', 0)}': {p.get('summary', p.get('type', 'Tactical pattern'))}" for p in patterns[:3]]
        while len(diagnosis) < 4:
            diagnosis.append("No additional verified tactical pattern is available yet.")
        recommendations = []
        if ht.get("shots", 0) and ht.get("xg", 0) / max(1, ht.get("shots", 0)) < .12:
            recommendations.append({"priority": "high", "action": f"Improve {h}'s shot selection",
                                    "rationale": f"{ht.get('shots', 0)} shots produced {ht.get('xg', 0)} xG."})
        if at.get("shots", 0) and at.get("xg", 0) / max(1, at.get("shots", 0)) < .12:
            recommendations.append({"priority": "high", "action": f"Improve {a}'s shot selection",
                                    "rationale": f"{at.get('shots', 0)} shots produced {at.get('xg', 0)} xG."})
        recommendations += [{"priority": "medium", "action": "Review the detected tactical pattern on video",
                             "rationale": p.get("summary", p.get("type", "Verified pattern"))} for p in patterns[:2]]
        if not recommendations:
            recommendations.append({"priority": "medium", "action": "Review the verified match timeline",
                                    "rationale": "No stable tactical pattern has been detected yet."})
        return {
            "executive_summary": f"{status} report at {e['clock']}: {score}. The report uses {e['data_source']} and only verified match evidence.",
            "tactical_diagnosis": diagnosis[:5],
            "player_notes": [{"player": p["name"], "note": f"Influence {p.get('influence', 0)}: {p.get('goals', 0)} goals, {p.get('xg', 0)} xG, {p.get('progressive_actions', 0)} progressive actions and {p.get('recoveries', 0)} recoveries."} for p in top],
            "recommendations": recommendations[:5],
            "training_plan": [
                {"theme": "Chance quality", "drill": "Constraint game: attacks must enter the box before finishing.", "success_measure": "Compare shot quality with the match baseline."},
                {"theme": "Tactical review", "drill": "Recreate the strongest detected pattern and rehearse the counter.", "success_measure": "Complete three clean rehearsals from each side."},
            ],
        }

    async def analyse(self, evidence: dict) -> dict:
        with span("coach_report.generate", match_id=evidence["match_id"], report_status=evidence["status"]):
            res = await self.llm.complete_json(system=PROMPT, user="EVIDENCE:\n" + json.dumps(evidence, default=str)[:16000],
                                               tier="large", fallback=lambda: self.fallback(evidence), max_tokens=1500,
                                               temperature=.25, interactive=True)
        report = res.data if isinstance(res.data, dict) else self.fallback(evidence)
        report["model"] = res.model
        return report

    def verify(self, report: dict, evidence: dict) -> dict:
        fallback = self.fallback(evidence)
        texts = {"executive_summary": report.get("executive_summary", "")}
        for key in ("tactical_diagnosis",):
            for i, value in enumerate(report.get(key) or []):
                texts[f"{key}_{i}"] = str(value)
        for key in ("player_notes", "recommendations", "training_plan"):
            for i, value in enumerate(report.get(key) or []):
                texts[f"{key}_{i}"] = " ".join(str(v) for v in value.values()) if isinstance(value, dict) else str(value)
        check = verify_output({"explanations": texts}, {"evidence": evidence, "valid_event_ids": []})
        allowed_minutes = {int(g["clock"].split(":")[0]) for g in evidence["goals"]}
        allowed_minutes |= {int(x.get("minute", 0)) for x in evidence["pattern_history"]}
        minute_issues = [key for key, text in texts.items() if bad_minutes(text, allowed_minutes)] if allowed_minutes else []
        issues = list(check["issues"]) + [f"{k}: unsupported minute" for k in minute_issues]
        bad = {i.split(":")[0] for i in issues}
        corrected = []
        if "executive_summary" in bad:
            report["executive_summary"] = fallback["executive_summary"]
            corrected.append("executive_summary")
        for key in ("tactical_diagnosis", "player_notes", "recommendations", "training_plan"):
            items = list(report.get(key) or [])
            safe = fallback[key]
            fixed = []
            for i, item in enumerate(items):
                if f"{key}_{i}" in bad:
                    corrected.append(f"{key}_{i}")
                    if i < len(safe):          # fail closed per item: swap in the deterministic, evidence-only version
                        fixed.append(safe[i])
                else:
                    fixed.append(item)
            report[key] = fixed or safe
        return {**report, "verification": {"passed": not issues, "issues": issues[:10], "corrected": corrected,
                                             "fallback_used": len(corrected) > len(texts) / 2, "evidence_locked": True}}

    def publish(self, report: dict, evidence: dict) -> dict:
        raw = json.dumps([evidence["match_id"], evidence["clock"], report], sort_keys=True, default=str).encode()
        report_id = hashlib.sha1(raw).hexdigest()[:16]
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORT_DIR / f"{report_id}.pdf"
        if not path.exists():
            self._pdf(path, report, evidence)
        return {**report, "report_id": report_id, "match_id": evidence["match_id"], "clock": evidence["clock"],
                "status": evidence["status"], "data_source": evidence["data_source"],
                "download_url": f"/api/reports/{report_id}.pdf"}

    def _pdf(self, path: Path, report: dict, evidence: dict) -> None:
        styles = getSampleStyleSheet()
        title = ParagraphStyle("ReportTitle", parent=styles["Title"], textColor=colors.HexColor("#082f49"),
                               alignment=TA_CENTER, fontSize=22, leading=27, spaceAfter=10)
        h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.HexColor("#0369a1"), spaceBefore=10)
        body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=9.5, leading=14)
        doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=16*mm, leftMargin=16*mm,
                                topMargin=14*mm, bottomMargin=14*mm,
                                title="Football Intelligence OS - Coach Report")
        score = " - ".join(f"{k} {v}" for k, v in evidence["score"].items())
        flow = [Paragraph("FOOTBALL INTELLIGENCE OS", title), Paragraph("COACH & PERFORMANCE REPORT", h2),
                Paragraph(f"{score} | {evidence['clock']} | {evidence['status'].replace('_', ' ').title()}", body), Spacer(1, 6),
                Paragraph("Executive summary", h2), Paragraph(report["executive_summary"], body)]

        def bullets(label: str, items: list) -> None:
            flow.append(Paragraph(label, h2))
            for item in items:
                text = item if isinstance(item, str) else " | ".join(f"<b>{k.replace('_', ' ').title()}:</b> {v}" for k, v in item.items())
                flow.append(Paragraph(f"- {text}", body)); flow.append(Spacer(1, 2))

        bullets("Tactical diagnosis", report.get("tactical_diagnosis", []))
        bullets("Player notes", report.get("player_notes", []))
        bullets("Recommendations", report.get("recommendations", []))
        bullets("Training plan", report.get("training_plan", []))
        flow += [Spacer(1, 10), Paragraph("Evidence appendix", h2)]
        totals = evidence["totals"]
        columns = ["Team", "Shots", "xG", "Possession", "PPDA", "Field tilt"]
        data = [columns] + [[team, vals.get("shots", "-"), vals.get("xg", "-"), f"{vals.get('possession_pct', '-')}%",
                            vals.get("ppda", "-"), f"{round(vals.get('field_tilt', 0) * 100, 1)}%"] for team, vals in totals.items()]
        table = Table(data, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0c4a6e")),
                                   ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .25, colors.grey),
                                   ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8),
                                   ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f0f9ff")])]))
        flow += [table, Spacer(1, 8), Paragraph(f"Source: {evidence['data_source']}. Verification: evidence locked; no prompt or private data stored in telemetry.", body)]
        doc.build(flow)
