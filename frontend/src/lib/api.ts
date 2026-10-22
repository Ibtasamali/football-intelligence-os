async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", "x-tenant-id": "demo", ...(init?.headers ?? {}) },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

const post = <T,>(path: string, body?: unknown) => req<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export const api = {
  health: () => req<any>("/health"),
  createMatch: (match_id: string) =>
    post<any>("/api/matches", { match_id, source: "synthetic", autostart: false, director: true, speed: 20 }),
  matchCatalog: () => req<any>("/api/catalog/matches"),
  match: (id: string) => req<any>(`/api/matches/${id}`),
  tactics: (id: string) => req<any>(`/api/matches/${id}/tactics`),
  timeline: (id: string) => req<any>(`/api/matches/${id}/timeline`),
  insights: (id: string) => req<any>(`/api/matches/${id}/insights?limit=200`),
  story: (id: string) => req<any>(`/api/matches/${id}/story`),
  positions: (id: string, ids: string[]) => post<any>(`/api/matches/${id}/events/positions`, ids),
  replay: (id: string, action: "start" | "pause") => post<any>(`/api/matches/${id}/replay/${action}`),
  speed: (id: string, speed: number, director?: boolean) => post<any>(`/api/matches/${id}/replay-speed`, { speed, director }),
  jump: (id: string, minute: number, seq?: number) => post<any>(`/api/matches/${id}/replay-jump`, { minute, seq }),
  trace: (match_id: string, insight_id?: string) => post<any>("/api/agents/trace", { match_id, insight_id }),
  whatif: (id: string, body: unknown) => post<any>(`/api/matches/${id}/whatif`, body),
  why: (insightId: string) => req<any>(`/api/insights/${insightId}/why`),
  ask: (match_id: string, text: string, user_id?: string, persona?: string, level?: string, language = "en") =>
    post<any>("/api/voice/query", { match_id, text, user_id, persona, level, language }),
  tts: async (text: string, persona?: string, language = "en"): Promise<Blob | null> => {
    const r = await fetch("/api/voice/tts", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text, persona, language }) });
    return r.ok ? r.blob() : null;
  },
  personas: () => req<any>("/api/voice/personas"),
  observability: () => req<any>("/api/agents/observability"),
  traces: (id?: string) => req<any>(`/api/agents/traces?limit=500${id ? `&match_id=${encodeURIComponent(id)}` : ""}`),
  desk: (match_id: string) => post<any>("/api/agents/desk", { match_id }),
  catalog: () => req<any>("/api/agents/catalog"),
  graph: () => req<any>("/api/agents/graph"),
  runs: (id: string) => req<any>(`/api/agents/runs?match_id=${id}&limit=20`),
  player: (pid: string, mid: string) => req<any>(`/api/players/${pid}?match_id=${mid}`),
  team: (tid: string, mid: string) => req<any>(`/api/teams/${tid}?match_id=${mid}`),
  fans: () => req<any>("/api/fans"),
  fan: (uid: string) => req<any>(`/api/fans/${uid}`),
  saveFan: (uid: string, body: unknown) => req<any>(`/api/fans/${uid}`, { method: "PUT", body: JSON.stringify(body) }),
  knowledge: (q: string) => req<any>(`/api/knowledge/search?q=${encodeURIComponent(q)}`),
  analyze: (match_id: string, event_id?: string) => post<any>("/api/agents/analyze", { match_id, event_id }),
};
