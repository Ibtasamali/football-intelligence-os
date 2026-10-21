"""Seed knowledge for RAG (historical archive + tactical library) and MAG (long-term memories).

The historical archive describes the *fictional* league the demo clubs play in, and is labelled
`synthetic` so the UI can disclose it. The tactical library contains general, well-established
football concepts (no club-specific facts).
"""
from __future__ import annotations

SOURCE_ARCHIVE = "Showcase League archive (synthetic demo data)"
SOURCE_LIBRARY = "Tactical knowledge library"

HISTORICAL_MATCHES = [
    {
        "doc_id": "hist_md07_azc_tha", "title": "Matchday 7 — Azure City FC 3–2 Thames Athletic",
        "date": "2025-10-04", "teams": ["azc", "tha"], "score": "3–2", "winner": "azc",
        "patterns": ["FLANK_OVERLOAD", "HIGH_PRESS", "TRANSITION_VULNERABILITY"],
        "players": ["tha_2", "tha_9", "azc_10", "azc_7"],
        "metrics": {"azc_ppda": 6.1, "tha_right_flank_share": 0.58, "azc_xg": 2.3, "tha_xg": 1.6},
        "text": ("Thames Athletic built their first-half attacks through an overload on the right flank: right-back "
                 "Kofi Mensah overlapped Leon Adeyemi and both Thames goals came from right-side crosses to Ethan Brooks. "
                 "Azure City responded after half-time by pressing high in Thames' build-up and shifting their attack to the "
                 "left. Thames chased the game late with both full-backs high, and Azure City won it with an 87th-minute "
                 "counter-attack finished by Theo Laurent after a long switch from Kai Moreno."),
    },
    {
        "doc_id": "hist_md19_tha_hbu", "title": "Matchday 19 — Thames Athletic 2–0 Harbour United",
        "date": "2026-01-17", "teams": ["tha", "hbu"], "score": "2–0", "winner": "tha",
        "patterns": ["DEEP_BLOCK", "FLANK_OVERLOAD"], "players": ["tha_2", "tha_15"],
        "metrics": {"tha_line_height_after_70": 19.5, "tha_xg_conceded_after_70": 0.2},
        "text": ("Leading 2–0, Thames Athletic introduced defensive midfielder Tomás Reyes and dropped into a deep block "
                 "with a defensive line below 20 metres. Harbour United had 71% possession in the final 20 minutes but "
                 "produced only 0.2 xG. The deep block worked because Thames were two goals ahead and kept their "
                 "full-backs at home."),
    },
    {
        "doc_id": "hist_md12_azc_kgt", "title": "Matchday 12 — Azure City FC 2–1 Kingsgate",
        "date": "2025-11-22", "teams": ["azc", "kgt"], "score": "2–1", "winner": "azc",
        "patterns": ["HIGH_PRESS", "SUBSTITUTION_IMPACT"], "players": ["azc_17", "azc_9", "azc_10"],
        "metrics": {"azc_ppda_second_half": 4.2, "azc_high_turnovers": 14},
        "text": ("Azure City trailed at half-time. Marta Varga brought on direct left winger Noah Kessler and switched "
                 "to an aggressive high press. Azure City recorded 14 high turnovers, and the equaliser came from a press "
                 "on Kingsgate's centre-back, Kai Moreno intercepting and Kessler setting up Marcus Hale with a cutback."),
    },
    {
        "doc_id": "hist_md15_wsm_azc", "title": "Matchday 15 — Westmoor 2–0 Azure City FC",
        "date": "2025-12-13", "teams": ["wsm", "azc"], "score": "2–0", "winner": "wsm",
        "patterns": ["TRANSITION_VULNERABILITY", "HIGH_PRESS"], "players": ["azc_4", "azc_5"],
        "metrics": {"azc_line_height": 44.0, "wsm_fast_transitions": 7},
        "text": ("Azure City's high press was bypassed with direct balls into the channels. With a defensive line of 44 "
                 "metres, Westmoor broke seven times in under 12 seconds after winning the ball and scored twice in "
                 "transition. A reminder that an aggressive press without rest-defence cover leaves space behind."),
    },
    {
        "doc_id": "hist_md03_tha_nfr", "title": "Matchday 3 — Thames Athletic 1–1 Northfield Rovers",
        "date": "2025-08-30", "teams": ["tha", "nfr"], "score": "1–1", "winner": None,
        "patterns": ["FLANK_OVERLOAD"], "players": ["tha_2", "tha_7", "tha_9"],
        "metrics": {"tha_right_flank_share": 0.61, "tha_crosses": 27},
        "text": ("Thames Athletic directed 61% of their attacking-half actions down the right, with Kofi Mensah "
                 "overlapping to deliver 11 crosses. Northfield doubled up on that flank after 60 minutes and the "
                 "overload stopped producing chances."),
    },
    {
        "doc_id": "hist_md22_azc_hbu", "title": "Matchday 22 — Azure City FC 4–0 Harbour United",
        "date": "2026-02-07", "teams": ["azc", "hbu"], "score": "4–0", "winner": "azc",
        "patterns": ["MIDFIELD_SUPERIORITY", "HIGH_PRESS"], "players": ["azc_10", "azc_6", "azc_8"],
        "metrics": {"azc_possession": 0.64, "azc_field_tilt": 0.71},
        "text": ("Azure City's midfield three of Demir, Brandt and Moreno created a central overload with field tilt of "
                 "71%. Harbour United's two-man midfield could not cope, and three of the four goals followed turnovers "
                 "won within 40 metres of goal."),
    },
    {
        "doc_id": "hist_md25_kgt_tha", "title": "Matchday 25 — Kingsgate 3–1 Thames Athletic",
        "date": "2026-03-01", "teams": ["kgt", "tha"], "score": "3–1", "winner": "kgt",
        "patterns": ["TRANSITION_VULNERABILITY", "DEEP_BLOCK"], "players": ["tha_2", "tha_3", "tha_19"],
        "metrics": {"tha_fullback_avg_x_last15": 71.0},
        "text": ("Level at 1–1 after 75 minutes, Thames brought on striker Jamal Pierce and pushed both full-backs "
                 "beyond 70 metres. Kingsgate scored twice on the counter in the final 12 minutes, both times attacking "
                 "the space vacated behind Kofi Mensah."),
    },
]

TACTICAL_LIBRARY = [
    ("lib_high_press", "High press and PPDA", ["HIGH_PRESS"],
     "PPDA (passes allowed per defensive action) measures pressing intensity: the opponent's passes in their own "
     "60% of the pitch divided by the pressing team's tackles, interceptions and fouls there. Lower means a more "
     "intense press. Sustained high pressing creates turnovers close to the opponent's goal, which tend to produce "
     "higher-quality chances because the defence is not set."),
    ("lib_counterpress", "Counter-pressing", ["HIGH_PRESS", "TRANSITION_VULNERABILITY"],
     "Counter-pressing means pressing immediately after losing the ball, while the opponent is still disorganised. "
     "It requires compact distances between players. If the first wave of pressure is bypassed, the space behind a "
     "high line becomes the main risk."),
    ("lib_flank_overload", "Flank overloads and overlapping full-backs", ["FLANK_OVERLOAD"],
     "A flank overload puts more attackers than defenders in a wide channel, often by having a full-back overlap the "
     "winger. It creates crossing positions and 2v1 situations. Defending teams respond by shifting the block across, "
     "doubling up on the full-back, or attacking the space the full-back leaves behind."),
    ("lib_deep_block", "Low / deep block", ["DEEP_BLOCK"],
     "A low block defends close to its own goal with compact lines, giving up possession to deny space behind. It is "
     "commonly used by teams protecting a lead (game-state effects). It limits high-quality chances but invites "
     "sustained pressure, crosses and second balls."),
    ("lib_rest_defence", "Rest defence and transition vulnerability", ["TRANSITION_VULNERABILITY"],
     "Rest defence is the structure a team keeps behind the ball while attacking. When full-backs push high and the "
     "defensive line advances, a turnover can leave few defenders against fast attackers, so counter-attacks reach the "
     "final third in a few seconds."),
    ("lib_midfield_superiority", "Numerical superiority in midfield", ["MIDFIELD_SUPERIORITY"],
     "Having more players than the opponent in the central zone gives free passing options between the lines and helps "
     "control territory (field tilt). Opponents usually respond by dropping a forward into midfield or narrowing."),
    ("lib_cutback", "Cutbacks", ["FLANK_OVERLOAD", "HIGH_PRESS"],
     "A cutback is a pass played backwards from near the byline into the area around the penalty spot. Cutbacks are "
     "among the highest-quality chance types because defenders are facing their own goal."),
    ("lib_field_tilt", "Field tilt", ["MIDFIELD_SUPERIORITY", "HIGH_PRESS"],
     "Field tilt is a team's share of final-third passes compared with the opponent. It shows territorial dominance more "
     "directly than possession, because possession can be sterile and deep."),
    ("lib_xg", "Expected goals (xG)", ["GOAL", "SHOT"],
     "xG estimates the probability that a shot becomes a goal, based on factors like distance, angle and shot type. It "
     "describes chance quality, not certainty: a 0.3 xG chance is scored about three times in ten."),
    ("lib_substitutions", "Substitution impact and game state", ["SUBSTITUTION_IMPACT", "DEEP_BLOCK"],
     "Substitutions change tactical structure as much as personnel: a defensive midfielder often signals a deeper block, "
     "an extra striker signals higher full-backs and more risk. Impact is best measured by comparing output in equal "
     "windows before and after the change."),
]

SEED_MEMORIES = [
    {"memory_id": "mem_tha_rightflank", "kind": "team_history", "entities": ["tha", "tha_2"],
     "text": "Across the synthetic season archive, Thames Athletic repeatedly attack through right-back Kofi Mensah's overlaps (Matchdays 3, 7, 25).",
     "source": SOURCE_ARCHIVE, "importance": 0.8},
    {"memory_id": "mem_tha_late_risk", "kind": "tactical_pattern", "entities": ["tha"],
     "text": "When Thames Athletic chase a result late they push both full-backs high, and they have conceded on the counter in that state (Matchdays 7 and 25).",
     "source": SOURCE_ARCHIVE, "importance": 0.85},
    {"memory_id": "mem_azc_kessler", "kind": "player_history", "entities": ["azc", "azc_17"],
     "text": "Noah Kessler has been Azure City's second-half impact substitute; on Matchday 12 he created the equaliser with a cutback after a high press.",
     "source": SOURCE_ARCHIVE, "importance": 0.7},
    {"memory_id": "mem_azc_press_risk", "kind": "tactical_pattern", "entities": ["azc"],
     "text": "Azure City's high press has been bypassed before: Westmoor broke seven times in transition against their 44 m line (Matchday 15).",
     "source": SOURCE_ARCHIVE, "importance": 0.75},
    {"memory_id": "mem_relationship_moreno_hale", "kind": "relationship", "entities": ["azc_10", "azc_9"],
     "text": "Kai Moreno → Marcus Hale is Azure City's most frequent final-third connection in the archive.",
     "source": SOURCE_ARCHIVE, "importance": 0.6},
    {"memory_id": "mem_user_alex_press", "kind": "conversation", "entities": ["azc"], "user_id": "alex",
     "text": "Alex previously asked why Azure City's pressing worked so well against Harbour United, and preferred short, visual explanations.",
     "source": "Fan conversation history", "importance": 0.9},
]

DEMO_FANS = [
    {"user_id": "alex", "display_name": "Alex", "favorite_team_id": "azc", "favorite_player_id": "azc_10",
     "knowledge_level": "intermediate", "language": "en", "persona": "casual_commentator", "interests": ["pressing", "tactics"]},
    {"user_id": "sam", "display_name": "Sam (Analyst)", "favorite_team_id": "tha", "favorite_player_id": "tha_2",
     "knowledge_level": "professional", "language": "en", "persona": "expert_analyst", "interests": ["set pieces", "data"]},
    {"user_id": "mia", "display_name": "Mia (age 9)", "favorite_team_id": "azc", "favorite_player_id": "azc_9",
     "knowledge_level": "beginner", "language": "en", "persona": "kids", "interests": ["goals"]},
]


def knowledge_documents() -> list[dict]:
    docs = []
    for h in HISTORICAL_MATCHES:
        docs.append({**h, "collection": "historical_matches", "source": SOURCE_ARCHIVE, "synthetic": True,
                     "text": f"{h['title']}. {h['text']}"})
    lib = []
    for doc_id, title, patterns, text in TACTICAL_LIBRARY:
        lib.append({"doc_id": doc_id, "title": title, "patterns": patterns, "teams": [], "players": [],
                    "collection": "knowledge_documents", "kind": "tactical_concept", "source": SOURCE_LIBRARY,
                    "synthetic": False, "text": f"{title}. {text}"})
    return docs + lib
