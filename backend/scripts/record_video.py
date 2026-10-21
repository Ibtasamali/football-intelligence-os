"""Record a narrated demo video automatically.

  .venv/bin/python scripts/record_video.py short-v2 → docs/video/fios-2min-v2.mp4 (new submission cut, < 2:00)
  .venv/bin/python scripts/record_video.py full-v2  → docs/video/fios-full-v2.mp4 (new 6–7 minute walkthrough)

The original `short` / `full` outputs remain supported. V2 modes intentionally use different filenames so the first
two videos are never overwritten.

How it works: a real Chrome plays the in-app Auto Demo while Playwright records the screen. The app logs every narration
line with a timestamp; afterwards each line is synthesised with Azure AI Speech and placed on the soundtrack at the same
moment (a later line cuts the previous one, exactly as in the app). ffmpeg muxes video + voice into an H.264 MP4.
Requires the backend (:8077) and website (:5188) to be running; run scripts/prewarm.py first for an instant demo.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import imageio_ffmpeg
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "video"
WORK = OUT / ".work"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1440, 900


def tts(text: str, persona: str | None, language: str | None, path: Path) -> bool:
    req = urllib.request.Request("http://localhost:8077/api/voice/tts", method="POST", headers={"content-type": "application/json"},
                                 data=json.dumps({"text": text[:1400], "persona": persona or "tactical_analyst",
                                                  "language": language or "en"}).encode())
    try:
        path.write_bytes(urllib.request.urlopen(req, timeout=60).read())
        return True
    except Exception as exc:  # noqa: BLE001
        print("  tts failed:", str(exc)[:120])
        return False


def duration(path: Path) -> float:
    out = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


async def record(mode: str) -> tuple[Path, float, float, list[dict], float]:
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True,
                                          args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                                "--autoplay-policy=no-user-gesture-required"])
        ctx = await browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(WORK),
                                        record_video_size={"width": W, "height": H}, device_scale_factor=1)
        page = await ctx.new_page()
        t_video0 = time.time()
        await page.goto("http://localhost:5188/?match=video-demo&tour=0", wait_until="load", timeout=120000)
        await page.wait_for_selector("text=Auto Demo", timeout=120000)
        await asyncio.sleep(2)
        # A clean, animated opening slate makes the first seconds readable even as a muted social preview.
        await page.evaluate("""() => {
          const el = document.createElement('div'); el.id = 'video-intro';
          el.innerHTML = `<div class="orb one"></div><div class="orb two"></div><div class="mark"><i></i></div>
            <div class="eyebrow">MICROSOFT AI · MULTI-AGENT FOOTBALL INTELLIGENCE</div>
            <div class="title">FOOTBALL<br/><span>INTELLIGENCE OS</span></div>
            <div class="tag">Every match. Every moment. Explained by AI.</div>
            <div class="proof">30 specialist agents&nbsp;&nbsp;·&nbsp;&nbsp;Verified evidence&nbsp;&nbsp;·&nbsp;&nbsp;Real-time 3D</div>`;
          const style = document.createElement('style'); style.id='video-intro-style'; style.textContent = `
            #video-intro{position:fixed;inset:0;z-index:99999;display:grid;place-content:center;text-align:center;overflow:hidden;background:radial-gradient(circle at 30% 10%,#123454 0,#060b18 42%,#02040a 100%);color:white;font-family:Inter,system-ui}
            #video-intro .orb{position:absolute;width:420px;height:420px;border-radius:50%;filter:blur(90px);opacity:.23;animation:pulse 2.4s ease-in-out infinite}.one{background:#22d3ee;left:-100px;top:-150px}.two{background:#7c3aed;right:-120px;bottom:-180px;animation-delay:.5s!important}
            #video-intro .mark{margin:0 auto 25px;width:70px;height:70px;border-radius:22px;display:grid;place-items:center;background:linear-gradient(135deg,#22d3ee,#2563eb);box-shadow:0 0 60px #22d3ee88;animation:rise .7s ease-out}.mark i{width:28px;height:28px;border:7px solid #06101c;border-radius:50%}
            #video-intro .eyebrow{font-size:14px;letter-spacing:.28em;color:#67e8f9;font-weight:700;animation:rise .8s .1s both}.title{font-size:70px;line-height:.92;font-weight:900;letter-spacing:-.045em;margin:20px 0;animation:rise .8s .2s both}.title span{background:linear-gradient(90deg,#67e8f9,#60a5fa,#c084fc);-webkit-background-clip:text;color:transparent}.tag{font-size:22px;color:#dbeafe;animation:rise .8s .3s both}.proof{margin-top:28px;font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#94a3b8;animation:rise .8s .4s both}@keyframes rise{from{opacity:0;transform:translateY(22px)}to{opacity:1;transform:none}}@keyframes pulse{50%{transform:scale(1.15);opacity:.34}}`;
          document.head.append(style); document.body.append(el);
        }""")
        await asyncio.sleep(2.8)
        await page.evaluate("() => { document.querySelector('#video-intro')?.remove(); document.querySelector('#video-intro-style')?.remove(); }")
        label = "🎬 2-min video" if mode.startswith("short") else "✦ Auto Demo"
        t_click = time.time()
        await page.get_by_role("button", name=label).click()
        print(f"recording '{mode}'…")
        started = False
        empty_polls = 0
        while time.time() - t_click < (200 if mode == "short" else 900):
            await asyncio.sleep(2)
            state = await page.evaluate("() => ({ready: !!window.__fios?.useStore, demo: window.__fios?.useStore?.getState()?.demo ?? null})")
            if not state["ready"]:  # tolerate a transient Vite/HMR frame during long recordings
                continue
            demo = state["demo"]
            if demo:
                started = True
                empty_polls = 0
                print(f"\r  {time.time() - t_click:5.0f}s  step {demo['step']}/{demo['total']}  {demo['caption'][:70]:70}", end="", flush=True)
            elif started:
                empty_polls += 1
                if empty_polls >= 3:
                    break
        await asyncio.sleep(1.5)
        t_end = time.time()
        speech = await page.evaluate("() => window.__fiosSpeech || []")
        await ctx.close()
        await browser.close()
    video = next(WORK.glob("*.webm"))
    print(f"\n  raw video {video.name}, {len(speech)} narration lines")
    return video, t_click - t_video0, t_end - t_video0, speech, t_video0


def build(mode: str, video: Path, t_start: float, t_end: float, speech: list[dict], t_video0_epoch: float) -> Path:
    lead = 2.8 if mode.endswith(("-v2", "-v3")) else 0.6
    start = max(0.0, t_start - lead)
    clips = []
    for i, s in enumerate(speech):
        at = s["t"] / 1000 - t_video0_epoch - start
        if at < -0.5:
            continue
        f = WORK / f"line_{i:03d}.mp3"
        if tts(s["text"], s.get("persona"), s.get("language"), f):
            clips.append((max(0.0, at), f))
    total = t_end - start
    inputs, filters = [], []
    for i, (at, f) in enumerate(clips):
        nxt = clips[i + 1][0] if i + 1 < len(clips) else total
        dur = max(0.3, min(duration(f), nxt - at))
        inputs += ["-i", str(f)]
        filters.append(f"[{i + 1}:a]atrim=0:{dur:.2f},asetpts=PTS-STARTPTS,adelay={int(at * 1000)}|{int(at * 1000)}[a{i}]")
    names = {"short": "fios-2min.mp4", "full": "fios-full.mp4",
             "short-v2": "fios-2min-v2.mp4", "full-v2": "fios-full-v2.mp4",
             "short-v3": "fios-2min-v3.mp4", "full-v3": "fios-full-v3.mp4"}
    out = OUT / names.get(mode, f"fios-{mode}.mp4")
    cmd = [FFMPEG, "-y", "-ss", f"{start:.2f}", "-t", f"{total:.2f}", "-i", str(video)] + inputs
    if clips:
        mix = "".join(f"[a{i}]" for i in range(len(clips))) + f"amix=inputs={len(clips)}:normalize=0:dropout_transition=0,loudnorm=I=-16:TP=-1.5:LRA=11,apad[aout]"
        cmd += ["-filter_complex", ";".join(filters + [mix]), "-map", "0:v", "-map", "[aout]", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "short-v2"
    OUT.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):  # a dev-server reload mid-recording loses the run → retry
        video, t_start, t_end, speech, t_video0 = await record(mode)
        if len(speech) >= (12 if mode.startswith("short") else 24):
            break
        print(f"  run looked incomplete ({len(speech)} narration lines) — retrying")
    out = build(mode, video, t_start, t_end, speech, t_video0)
    d = duration(out)
    print(f"✅ {out}  ({d:.1f}s)")
    if mode.startswith("short") and d >= 119.5:
        print("⚠ longer than 2:00 — the hackathon limit. Re-run (Azure was slow) or trim before uploading.")


if __name__ == "__main__":
    asyncio.run(main())
