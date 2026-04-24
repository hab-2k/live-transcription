import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class EventBroadcaster:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)

    async def publish(self, session_id: str, event: dict[str, Any]) -> None:
        self._history[session_id].append(event)
        dead: list[WebSocket] = []
        for websocket in list(self._connections[session_id]):
            try:
                await websocket.send_json(event)
            except Exception:
                dead.append(websocket)
        for ws in dead:
            self._connections[session_id].discard(ws)

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[session_id].add(websocket)
        logger.info("WebSocket connected for session %s", session_id)

        for event in self._history.get(session_id, []):
            await websocket.send_json(event)

        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            self._connections[session_id].discard(websocket)
            logger.info("WebSocket disconnected for session %s", session_id)
            return


broadcaster = EventBroadcaster()
