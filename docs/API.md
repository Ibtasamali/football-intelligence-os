# API Reference

Interactive OpenAPI docs: `http://localhost:8077/docs`. Auth: none in demo mode; set `API_KEYS` (header
`x-api-key`) or `AUTH_JWT_ISSUER`/`AUTH_JWT_AUDIENCE` (Entra ID bearer token). Tenant: `x-tenant-id`.

## Matches
| Method | Path | Description |
|---|---|---|
| GET | `/api/catalog/matches` | Available matches: synthetic demo + real StatsBomb matches (`wc2022-final`, `euro2024-final`, `wc2022-sf-arg-cro`) |
| POST | `/api/matches` | Create/reset a match `{match_id, source:"synthetic"\|"statsbomb", statsbomb_key?, autostart, speed, director}`. Real matches also build the real historical archive in the background (`archive_ready` WS message) |
| GET | `/api/matches` | Loaded matches with replay status |
| GET | `/api/matches/{id}` | Teams, roster, CAG context, engine snapshot, last event with positions |
| GET | `/api/matches/{id}/insights` | Published insights (`?category=GOAL`) |
| GET | `/api/matches/{id}/timeline` | Key-moment timeline and momentum series |
| GET | `/api/matches/{id}/tactics` | Patterns, formations, totals, 5-min window, networks, influence, predictions, avg positions |
| GET | `/api/matches/{id}/events` | Event log (`?from_seq=&limit=&positions=true`) |
| POST | `/api/matches/{id}/events/positions` | Body: list of event IDs → events with positions (3D replay) |
| GET | `/api/matches/{id}/story` | AI match story (5 moments, how it was won, player of the match, tactical battle, missed chance) |
| POST | `/api/matches/{id}/replay/start` · `/pause` | Replay control |
| POST | `/api/matches/{id}/replay-speed` | `{speed, director}` |
| POST | `/api/matches/{id}/replay-jump` | `{minute}` or `{seq}` (event index; used for real clocks): fast path only, no LLM |

## Events
| Method | Path | Description |
|---|---|---|
| POST | `/api/events` | Ingest one `MatchEvent` from a live provider (role `analyst`) |

## Agents
| Method | Path | Description |
|---|---|---|
| POST | `/api/agents/analyze` | Force a full LangGraph run for an event `{match_id, event_id?}` |
| GET | `/api/agents/catalog` | The 30 agents with family / LLM usage |
| GET | `/api/agents/observability` | Counters, per-agent latency/confidence/tokens, model usage, worker pool |
| GET | `/api/agents/runs?match_id=` | Traced graph runs (`agent_run_id`, path, duration, tokens) |
| GET | `/api/agents/graph` | Mermaid diagrams of the compiled event and query graphs |

## Voice and Q&A
| Method | Path | Description |
|---|---|---|
| POST | `/api/voice/query` | `{match_id, text, user_id?, persona?, level?, language?}` → answer insight (query graph). Non-English questions are translated in and the answer is returned in `localized` |
| POST | `/api/voice/tts` | `{text, persona, language}` → `audio/mpeg` (Azure neural voice per language, cached) |
| GET | `/api/voice/languages` | 14 supported languages with locale and RTL flag |
| POST | `/api/voice/stt` | multipart audio → `{text}` (Azure Speech short-utterance) |
| GET | `/api/voice/personas` | Personas and voices |

## Insights, players, teams, fans, knowledge
| Method | Path | Description |
|---|---|---|
| GET | `/api/insights/{id}` · `/why` | Insight · full evidence (claims, events, docs, memories, path, routing, RAG trace) |
| POST | `/api/insights/{id}/translate` | `{language, level, persona}` → verified translation (numbers + names re-checked; cached per language) |
| GET | `/api/players/{id}?match_id=` | Profile, match stats, influence rank, connections, touch map, memories |
| GET | `/api/teams/{id}?match_id=` | Team totals, network, patterns, archive, memories |
| GET/PUT | `/api/fans/{user_id}` | Fan profile (team, player, level, persona) and personal memories |
| GET | `/api/knowledge/search?q=` | Vector search over archive and tactical library |
| POST | `/api/knowledge/text` · `/upload` | Index text, or a PDF via Azure Document Intelligence |

## WebSocket `/ws/matches/{match_id}`
| `type` | Payload |
|---|---|
| `hello` | recent insights |
| `event` | event with 22 positions, score, momentum, significance, category, `pattern_changes`, periodic `context` |
| `run_started` | run_id, event_id, significance, category, reasons |
| `routing` | router plan: waves, memory/retrieval decisions, model tier |
| `agent_status` | agent, status, latency_ms, confidence, model, tokens, evidence count |
| `insight` | full insight incl. explanations, predictions, claims, provenance, 3D commands, voice scripts |
| `run_complete` | duration, tokens, graph path, cache hit |
| `jumped` · `replay_finished` | replay control events |
