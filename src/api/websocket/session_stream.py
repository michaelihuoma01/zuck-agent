"""WebSocket session streaming endpoint."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_db
from src.core.session_manager import SessionManager
from src.core.agent_runtime import AgentRuntime
from src.core.exceptions import SessionNotFoundError, SessionStateError
from src.core.constants import MessageType
from src.api.deps import get_agent_runtime
from src.api.security import verify_websocket_api_key
from src.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Thread-safe manager for WebSocket connections."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            if session_id not in self._connections:
                self._connections[session_id] = []
            self._connections[session_id].append(websocket)
        logger.info(f"WebSocket connected for session {session_id}")

    async def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if session_id in self._connections:
                try:
                    self._connections[session_id].remove(websocket)
                    if not self._connections[session_id]:
                        del self._connections[session_id]
                except ValueError:
                    pass
        logger.info(f"WebSocket disconnected for session {session_id}")

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        """Broadcast a message to all connections for a session concurrently."""
        async with self._lock:
            connections = self._connections.get(session_id, []).copy()

        if not connections:
            return

        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()

        message_json = json.dumps(message)

        # Send concurrently to all connections
        async def safe_send(ws: WebSocket) -> tuple[WebSocket, bool]:
            try:
                await ws.send_text(message_json)
                return ws, True
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                return ws, False

        results = await asyncio.gather(
            *[safe_send(conn) for conn in connections],
            return_exceptions=True
        )

        # Remove failed connections
        for result in results:
            if isinstance(result, tuple):
                ws, success = result
                if not success:
                    await self.disconnect(ws, session_id)

    async def stream_from_runtime(
        self,
        session_id: str,
        runtime: AgentRuntime,
    ) -> None:
        """Stream agent messages to all WebSocket connections."""
        if not runtime.is_session_active(session_id):
            return

        try:
            client = runtime._active_clients.get(session_id)
            if not client:
                return

            async for message in runtime._stream_response(client, session_id):
                await self.broadcast(session_id, message)

        except Exception as e:
            logger.exception(f"Error streaming to session {session_id}")
            await self.broadcast(session_id, {
                "type": MessageType.ERROR.value,
                "content": str(e),
            })

    def get_connection_count(self, session_id: str) -> int:
        """Get the number of active connections for a session."""
        return len(self._connections.get(session_id, []))


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws/sessions/{session_id}")
async def websocket_session_stream(
    websocket: WebSocket,
    session_id: str,
    api_key: str | None = Query(None, alias="api_key"),
    db: AsyncSession = Depends(get_db),
) -> None:
    """WebSocket endpoint for real-time session message streaming.

    Authentication via query parameter: ?api_key=xxx
    Or via X-API-Key header during handshake.

    Message format (JSON):
    {
        "type": "text" | "tool_use" | "tool_result" | "result" | "status" | "error",
        "content": "...",
        "timestamp": "2026-02-05T10:00:00Z"
    }

    Client commands:
    {"command": "ping"} -> {"type": "pong", "timestamp": "..."}
    {"command": "interrupt"} -> Interrupts active session
    {"command": "subscribe"} -> Re-subscribes to session updates
    """
    settings = get_settings()
    stream_task: asyncio.Task | None = None

    # Authenticate
    try:
        await verify_websocket_api_key(websocket, settings)
    except Exception:
        return  # WebSocket already closed by verify_websocket_api_key

    # Verify session exists
    session_manager = SessionManager(db)
    try:
        session = await session_manager.get_session(session_id)
    except SessionNotFoundError:
        await websocket.close(code=4004, reason="Session not found")
        return

    # Accept connection
    await manager.connect(websocket, session_id)

    try:
        # Send current session status
        await websocket.send_text(json.dumps({
            "type": MessageType.STATUS.value,
            "status": session.status,
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))

        # Send recent message history
        messages = await session_manager.get_messages(session_id, limit=50)
        if messages:
            await websocket.send_text(json.dumps({
                "type": MessageType.HISTORY.value,
                "messages": [
                    {
                        "role": m.role,
                        "content": m.content,
                        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                    }
                    for m in messages
                ],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))

        # Get runtime for streaming
        runtime = get_agent_runtime(settings)

        # Start streaming if session is active
        if runtime.is_session_active(session_id):
            stream_task = asyncio.create_task(
                manager.stream_from_runtime(session_id, runtime)
            )

        # Handle incoming client commands
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                command = message.get("command")

                if command == "ping":
                    await websocket.send_text(json.dumps({
                        "type": MessageType.PONG.value,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))

                elif command == "interrupt":
                    if runtime.is_session_active(session_id):
                        # Disconnect client (kills stream, unblocks background task)
                        await runtime.disconnect_session(session_id)

                        # Transition to error state
                        try:
                            await session_manager.fail_session(
                                session_id, "Session interrupted by user"
                            )
                        except Exception:
                            pass  # May already be terminal from disconnect cascade

                        await websocket.send_text(json.dumps({
                            "type": MessageType.STATUS.value,
                            "status": "error",
                            "session_id": session_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }))
                    else:
                        await websocket.send_text(json.dumps({
                            "type": MessageType.ERROR.value,
                            "content": "Session is not active",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }))

                elif command == "subscribe":
                    # Re-subscribe if session became active
                    if runtime.is_session_active(session_id):
                        if stream_task is None or stream_task.done():
                            stream_task = asyncio.create_task(
                                manager.stream_from_runtime(session_id, runtime)
                            )

                else:
                    await websocket.send_text(json.dumps({
                        "type": MessageType.ERROR.value,
                        "content": f"Unknown command: {command}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))

            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": MessageType.ERROR.value,
                    "content": "Invalid JSON",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")

    except Exception as e:
        logger.exception(f"WebSocket error for session {session_id}")
        try:
            await websocket.send_text(json.dumps({
                "type": MessageType.ERROR.value,
                "content": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
        except Exception:
            pass

    finally:
        # Cancel streaming task if running
        if stream_task is not None and not stream_task.done():
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass

        await manager.disconnect(websocket, session_id)


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager."""
    return manager
