"""Conversations with the tutor. Turns stream back as Server-Sent Events, one AgentEvent per
`data:` line, and are saved as they go."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime, BaseModel

from pupil_server.agents.sessions import SessionBusy
from pupil_server.conversations.service import Conversations
from pupil_server.conversations.transcript import (
    Prompt,
    QuizResults,
    TranscriptItem,
    UserMessage,
)
from pupil_server.db import LOCAL_LEARNER, NotFound
from pupil_server.db.learning import AttemptRepo, QuizRepo
from pupil_server.learning.quiz import describe_attempt

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

# One learner until remote mode adds accounts.
LEARNER = LOCAL_LEARNER


class ConversationOut(BaseModel):
    conversation_id: str
    created_at: AwareDatetime


class ConversationWithTranscript(ConversationOut):
    transcript: list[TranscriptItem]


class MessageIn(BaseModel):
    text: str


class QuizResultsIn(BaseModel):
    attempt_id: str


def _conversations(request: Request) -> Conversations:
    return request.app.state.conversations


def _not_found() -> HTTPException:
    return HTTPException(404, "no such conversation")


@router.post("", status_code=201)
async def start(request: Request) -> ConversationOut:
    conversation = await _conversations(request).start(LEARNER)
    return ConversationOut(conversation_id=conversation.id, created_at=conversation.created_at)


@router.get("")
async def list_recent(request: Request) -> list[ConversationOut]:
    return [
        ConversationOut(conversation_id=c.id, created_at=c.created_at)
        for c in await _conversations(request).list_recent(LEARNER)
    ]


@router.get("/{conversation_id}")
async def get(conversation_id: str, request: Request) -> ConversationWithTranscript:
    conversations = _conversations(request)
    try:
        conversation = await conversations.get(LEARNER, conversation_id)
        transcript = await conversations.transcript(LEARNER, conversation_id)
    except NotFound:
        raise _not_found() from None
    return ConversationWithTranscript(
        conversation_id=conversation.id,
        created_at=conversation.created_at,
        transcript=transcript,
    )


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str, body: MessageIn, request: Request
) -> StreamingResponse:
    return await _turn(request, conversation_id, UserMessage(text=body.text))


@router.post("/{conversation_id}/quiz-results")
async def report_quiz_results(
    conversation_id: str, body: QuizResultsIn, request: Request
) -> StreamingResponse:
    """Tell the agent how the learner did on a quiz, and stream its reply.

    The app writes the message from the stored attempt, so the agent hears exactly what was
    graded.
    """
    db = request.app.state.db
    attempts = AttemptRepo(db)
    try:
        attempt = await attempts.get(LEARNER, body.attempt_id)
        results = await attempts.results(LEARNER, body.attempt_id)
        quiz = await QuizRepo(db).get(LEARNER, attempt.quiz_id)
    except NotFound:
        raise HTTPException(404, "no such attempt") from None
    prompt = QuizResults(
        quiz_id=quiz.id,
        attempt_id=attempt.id,
        correct=sum(r.correct for r in results),
        total=len(results),
        text=describe_attempt(quiz, attempt, results),
    )
    return await _turn(request, conversation_id, prompt)


async def _turn(request: Request, conversation_id: str, prompt: Prompt) -> StreamingResponse:
    conversations = _conversations(request)
    try:
        entry = await conversations.claim(LEARNER, conversation_id)
    except NotFound:
        raise _not_found() from None
    except SessionBusy:
        raise HTTPException(409, "a turn is already running in this conversation") from None
    except Exception as exc:
        raise HTTPException(502, f"could not start agent: {exc or type(exc).__name__}") from exc

    async def stream() -> AsyncIterator[str]:
        async for event in conversations.send(LEARNER, conversation_id, entry, prompt):
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.delete("/{conversation_id}/session", status_code=204)
async def release(conversation_id: str, request: Request) -> Response:
    """Let go of the live agent session; the conversation is kept and can carry on later."""
    try:
        await _conversations(request).release(LEARNER, conversation_id)
    except NotFound:
        raise _not_found() from None
    return Response(status_code=204)
