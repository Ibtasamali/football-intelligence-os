"""WebSocket stream: events, insights, agent status, predictions, 3D commands, voice status."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/matches/{match_id}")
async def match_socket(ws: WebSocket, match_id: str):
    c = ws.app.state.container
    await c.broadcaster.connect(match_id, ws)
    try:
        rt = c.runtimes.get(match_id)
        await c.broadcaster.send_to(ws, match_id, {"type": "hello", "match_id": match_id, "loaded": bool(rt),
                                       "insights": [i.model_dump() for i in rt.insights[-30:]] if rt else []})
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await c.broadcaster.send_to(ws, match_id, {"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        c.broadcaster.disconnect(match_id, ws)
