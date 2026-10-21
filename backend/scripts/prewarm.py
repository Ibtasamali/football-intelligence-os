"""Prepare the demo: run the synthetic demo match once through the full AI pipeline so every insight, story and
key translation is cached (7 days). Afterwards the live demo is instant and costs 0 tokens.

  .venv/bin/python scripts/prewarm.py
"""
import json
import sys
import time
import urllib.request

API = "http://localhost:8077"
MATCH = sys.argv[1] if len(sys.argv) > 1 else "live-demo"


def call(path, body=None, timeout=120):
    req = urllib.request.Request(API + path, method="POST" if body is not None else "GET",
                                 headers={"content-type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def main():
    try:
        call("/health")
    except Exception:
        sys.exit("Backend is not running — start it first (double-click START FOOTBALL AI.command).")
    print("1/4  Loading the synthetic demo match (Azure City FC vs Thames Athletic)…")
    call("/api/matches", {"match_id": MATCH, "source": "synthetic", "speed": 90, "director": False, "autostart": True})
    t0 = time.time()
    while True:
        st = call(f"/api/matches/{MATCH}/replay")
        print(f"\r2/4  AI analysing the match: {st['clock']}  ({st['index']}/{st['total']} events)   ", end="", flush=True)
        if st["finished"] or st["index"] >= st["total"]:
            break
        time.sleep(3)
    print("\n     waiting for the last AI analyses to finish…")
    time.sleep(45)
    ins = call(f"/api/matches/{MATCH}/insights?limit=500")["insights"]
    print(f"     {len(ins)} insights cached in {time.time() - t0:.0f}s")
    print("3/4  Generating the match story…")
    call(f"/api/matches/{MATCH}/story", timeout=180)
    print("4/4  Translating key moments (Urdu, Arabic, Spanish)…")
    key = sorted((i for i in ins if i["significance"] >= 0.6), key=lambda i: -i["significance"])[:12]
    for lang in ("ur", "ar", "es"):
        for i in key:
            try:
                call(f"/api/insights/{i['insight_id']}/translate", {"language": lang, "level": "intermediate", "persona": "casual_commentator"})
            except Exception:
                pass
    call("/api/matches", {"match_id": MATCH, "source": "synthetic"})  # reset to 0:00 for the live demo
    print("✅ Demo prepared. Open the website and press ✦ Auto Demo (or START MATCH).")


if __name__ == "__main__":
    main()
