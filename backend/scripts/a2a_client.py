"""Minimal A2A client: discover the agent card, then send tasks — e.g. a broadcaster's agent asking for a recap.

  .venv/bin/python scripts/a2a_client.py "Why did Thames Athletic score?"
  .venv/bin/python scripts/a2a_client.py "/recap es"
"""
import json
import sys
import urllib.request
import uuid

BASE = "http://localhost:8077"
card = json.load(urllib.request.urlopen(f"{BASE}/.well-known/agent-card.json"))
print(f"Discovered agent: {card['name']} — skills: {', '.join(s['id'] for s in card['skills'])}")
text = sys.argv[1] if len(sys.argv) > 1 else "What just happened?"
body = {"jsonrpc": "2.0", "id": 1, "method": "message/send",
        "params": {"message": {"role": "user", "messageId": str(uuid.uuid4()), "parts": [{"kind": "text", "text": text}]}}}
req = urllib.request.Request(card["url"], data=json.dumps(body).encode(), headers={"content-type": "application/json"})
res = json.load(urllib.request.urlopen(req, timeout=240))["result"]
print("\nAnswer:", res["parts"][0]["text"])
print("Data:  ", json.dumps(res["parts"][1]["data"], ensure_ascii=False)[:600])
