import os

os.environ["ENVIRONMENT"] = "test"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402

main.settings.environment = "test"


def test_api_end_to_end():
    with TestClient(main.app) as client:
        assert client.get("/health").json()["status"] == "ok"
        r = client.post("/api/matches", json={"match_id": "api-match", "autostart": False})
        assert r.status_code == 200 and r.json()["events_available"] > 1500
        with client.websocket_connect("/ws/matches/api-match") as ws:
            assert ws.receive_json()["type"] == "hello"
            client.post("/api/matches/api-match/replay-jump", json={"minute": 3})
            kinds = set()
            for _ in range(10):
                kinds.add(ws.receive_json()["type"])
            assert "event" in kinds
        m = client.get("/api/matches/api-match").json()
        assert m["snapshot"]["minute"] >= 2 and len(m["last_event"]["positions"]) == 22
        t = client.get("/api/matches/api-match/tactics").json()
        assert "predictions" in t and t["formations"]["azc"]["live"]
        a = client.post("/api/voice/query", json={"match_id": "api-match", "text": "Who is the best player?", "user_id": "alex"})
        assert a.status_code == 200
        ans = a.json()["answer"]
        why = client.get(f"/api/insights/{ans['insight_id']}/why").json()
        assert why["agents_used"] and why["graph_path"]
        assert client.get("/api/agents/catalog").json()["agents"].__len__() == 30
        obs = client.get("/api/agents/observability").json()
        assert obs["counters"]["events_ingested"] > 0
        desk = client.post("/api/agents/desk", json={"match_id": "api-match"})
        assert desk.status_code == 200
        report = desk.json()
        assert report["framework"] == "Microsoft Agent Framework" and len(report["stages"]) == 4
        assert report["report"]["verification"]["evidence_locked"]
        pdf = client.get(report["report"]["download_url"])
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        trace = client.get("/api/agents/traces?match_id=api-match").json()
        assert trace["span_count"] > 0 and trace["sensitive_data_captured"] is False
        card = client.get("/.well-known/agent-card.json").json()
        assert {s["id"] for s in card["skills"]} == {"match_qa", "match_status", "recap"}
        a2a = client.post("/a2a", json={"jsonrpc": "2.0", "id": 7, "method": "SendMessage",
                           "params": {"message": {"parts": [{"text": "status"}],
                                                    "metadata": {"match_id": "api-match", "skill": "match_status"}}}})
        assert a2a.status_code == 200 and a2a.json()["result"]["message"]["role"] == "ROLE_AGENT"
        assert "graph TD" in client.get("/api/agents/graph").json()["event_graph"]
        assert client.post("/api/voice/query", json={"match_id": "api-match", "text": ""}).status_code == 422
        assert client.get("/api/players/azc_10?match_id=api-match").json()["player"]["name"] == "Kai Moreno"
        assert client.put("/api/fans/newfan", json={"knowledge_level": "beginner", "favorite_team_id": "tha"}).json()["knowledge_level"] == "beginner"
