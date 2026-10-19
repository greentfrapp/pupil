"""Chat with an agent. Turns stream back as Server-Sent Events, one AgentEvent per `data:` line."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from pupil_server.agents.demo import demo_config
from pupil_server.agents.sessions import SessionBusy, SessionNotFound, SessionStore

router = APIRouter(prefix="/api/chat", tags=["chat"])


class SessionCreated(BaseModel):
    session_id: str


class MessageIn(BaseModel):
    text: str


def _store(request: Request) -> SessionStore:
    return request.app.state.agents


@router.post("/sessions", status_code=201)
async def create_session(request: Request) -> SessionCreated:
    try:
        session_id = await _store(request).open(demo_config())
    except Exception as exc:
        raise HTTPException(502, f"could not start agent: {exc}") from exc
    return SessionCreated(session_id=session_id)


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: MessageIn, request: Request) -> StreamingResponse:
    store = _store(request)
    try:
        entry = store.claim(session_id)
    except SessionNotFound:
        raise HTTPException(404, "no such session") from None
    except SessionBusy:
        raise HTTPException(409, "a turn is already running on this session") from None

    async def stream() -> AsyncIterator[str]:
        async for event in store.send(entry, body.text):
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request) -> Response:
    try:
        await _store(request).close(session_id)
    except SessionNotFound:
        raise HTTPException(404, "no such session") from None
    return Response(status_code=204)
