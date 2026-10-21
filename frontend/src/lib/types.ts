export type TeamId = string;

export interface Position { player_id: string; team_id: TeamId; x: number; y: number }

export interface MatchEvent {
  event_id: string; seq: number; clock: string; type: string; team: TeamId | null; player: string | null;
  player_id: string | null; outcome: string | null; x: number | null; y: number | null;
  end_x: number | null; end_y: number | null; xg?: number | null; positions?: Position[];
  meta?: Record<string, unknown>; related_player_id?: string | null;
}

export interface Prediction { label: string; probability: number; horizon: string; basis: string; kind: string }

export interface Claim { text: string; event_ids: string[]; metric_refs: string[]; verified: boolean; reason: string }

export interface Pattern {
  type: string; team_id: TeamId; confidence: number; summary: string; metrics: Record<string, unknown>;
  evidence_event_ids: string[]; zone: string; players: string[]; started_minute: number; status?: string;
}

export interface SceneCommand {
  type: "highlight_zone" | "highlight_players" | "trajectory" | "passing_lanes" | "pulse" | "camera" | "replay" | "defensive_line" | string;
  [k: string]: any;
}

export interface Provenance {
  source_events: string[]; retrieved_documents: any[]; memories: any[]; model: string; agents_used: string[];
  confidence: number; timestamp: number; cache_hit: boolean; graph_path: string[];
}

export interface Insight {
  insight_id: string; match_id: string; event_id: string | null; minute: number; second: number; category: string;
  headline: string; explanations: Record<string, string>; commentary: string; perspectives: Record<string, string>;
  voice_scripts: Record<string, string>; historical_note: string; verification: any; significance: number;
  team_id: TeamId | null; player_ids: string[]; claims: Claim[]; predictions: Prediction[]; patterns: Pattern[];
  statistics: Record<string, any>; visualization: SceneCommand[]; provenance: Provenance; created_at: number;
}

export interface TeamMeta { name: string; short: string; colors: { primary: string; secondary: string }; formation: string; coach: string; style: string }

export interface Player { player_id: string; team_id: TeamId; name: string; number: number; position: string; role: string; bench: boolean }

export interface AgentStatus {
  agent: string; status: string; latency_ms: number; confidence: number; model: string; tokens: number; evidence: number;
  at: number; run_id?: string; error?: string | null;
}

export interface FanProfile {
  user_id: string; display_name: string; favorite_team_id: TeamId | null; favorite_player_id: string | null;
  knowledge_level: "beginner" | "intermediate" | "advanced" | "professional"; persona: string; language: string; interests: string[];
}

export interface JumpPoint { minute: number; label: string; seq?: number }

export interface ReplayStatus { index: number; total: number; running: boolean; speed: number; director: boolean; finished: boolean; clock: string }
