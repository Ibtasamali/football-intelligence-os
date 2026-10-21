"""Real-time fan-out.

LocalBroadcaster keeps WebSocket connections in-process (dev, single replica). In Azure, set
AZURE_WEB_PUBSUB_CONNECTION_STRING and messages are sent to a Web PubSub group per match, so any
number of API replicas can publish and millions of clients can subscribe without sticky sessions.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from collections import defaultdict

import httpx
from fastapi import WebSocket

from app.core.logging import get_logger

log = get_logger("broadcast")


LOW_PRIORITY = {"event", "agent_status", "routing", "run_started"}  # skippable when a viewer falls behind


class _Conn:
    """One subscriber with its own outbox and sender task, so a slow client never blocks ingest.
    When a viewer falls behind, routine messages (player positions, agent ticks) are skipped; insights, goals and
    pattern changes are always delivered. Only a hopelessly stuck client is disconnected."""

    SOFT, HARD = 120, 3000

    def __init__(self, ws: WebSocket, maxsize: int = 3000) -> None:
        self.ws = ws
        self.q: asyncio.Queue[str] = asyncio.Queue(maxsize=maxsize)
        self.alive = True
        self.skipped = 0
        self.task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        try:
            while self.alive:
                await self.ws.send_text(await self.q.get())
        except Exception:  # noqa: BLE001 — client gone
            self.alive = False

    def offer(self, data: str, kind: str = "", important: bool = False) -> bool:
        if not self.alive:
            return False
        if self.q.qsize() > self.SOFT and kind in LOW_PRIORITY and not important:
            self.skipped += 1
            return True
        try:
            self.q.put_nowait(data)
            return True
        except asyncio.QueueFull:  # slow consumer: drop it rather than stall the match pipeline
            self.alive = False
            self.task.cancel()
            asyncio.create_task(self._close())  # the client auto-reconnects and resyncs via "hello"
            return False

    async def _close(self) -> None:
        try:
            await self.ws.close(code=1013)
        except Exception:  # noqa: BLE001
            pass


class LocalBroadcaster:
    def __init__(self) -> None:
        self.rooms: dict[str, dict[WebSocket, _Conn]] = defaultdict(dict)
        self.dropped = 0

    async def connect(self, match_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.rooms[match_id][ws] = _Conn(ws)

    def disconnect(self, match_id: str, ws: WebSocket) -> None:
        conn = self.rooms[match_id].pop(ws, None)
        if conn:
            conn.alive = False
            conn.task.cancel()

    def subscribers(self, match_id: str) -> int:
        return len(self.rooms.get(match_id, ()))

    async def send_to(self, ws: WebSocket, match_id: str, message: dict) -> None:
        conn = self.rooms.get(match_id, {}).get(ws)
        if conn:
            conn.offer(json.dumps(message, default=str), message.get("type", ""), True)

    async def send(self, match_id: str, message: dict) -> None:
        room = self.rooms.get(match_id)
        if not room:
            return
        data = json.dumps(message, default=str)
        kind = message.get("type", "")
        important = bool(message.get("pattern_changes")) or (message.get("event") or {}).get("type") in ("GOAL", "SHOT", "CARD", "SUBSTITUTION", "HALF_TIME", "FULL_TIME")
        for ws, conn in list(room.items()):
            if not conn.offer(data, kind, important):
                room.pop(ws, None)
                self.dropped += 1
                log.warning("slow_subscriber_dropped", match_id=match_id)


class AzureWebPubSubBroadcaster(LocalBroadcaster):
    """Publishes to Azure Web PubSub groups via REST (HS256 JWT signed with the access key)."""

    def __init__(self, connection_string: str, hub: str = "matches") -> None:
        super().__init__()
        parts = dict(p.split("=", 1) for p in connection_string.split(";") if "=" in p)
        self.endpoint = parts["Endpoint"].rstrip("/")
        self.key = parts["AccessKey"]
        self.hub = hub
        self.client = httpx.AsyncClient(timeout=5)

    def _token(self, url: str) -> str:
        def b64(d: bytes) -> str:
            return base64.urlsafe_b64encode(d).rstrip(b"=").decode()
        header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        payload = b64(json.dumps({"aud": url, "exp": int(time.time()) + 300}).encode())
        sig = hmac.new(self.key.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        return f"{header}.{payload}.{b64(sig)}"

    async def send(self, match_id: str, message: dict) -> None:
        await super().send(match_id, message)  # local sockets too
        url = f"{self.endpoint}/api/hubs/{self.hub}/groups/{match_id}/:send?api-version=2024-01-01"
        try:
            await self.client.post(url, content=json.dumps(message, default=str),
                                   headers={"Authorization": f"Bearer {self._token(url)}", "Content-Type": "application/json"})
        except Exception as exc:  # noqa: BLE001
            log.warning("webpubsub_send_failed", error=str(exc)[:200])


def create_broadcaster():
    cs = os.getenv("AZURE_WEB_PUBSUB_CONNECTION_STRING", "")
    return AzureWebPubSubBroadcaster(cs) if cs else LocalBroadcaster()
