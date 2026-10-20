"""Taking a quiz: the learner's view of it, without answers, and submitting their answers.

Answers go straight from the quiz screen to the grader, never through the agent. A quiz is
answered once; after that it shows the results.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from pupil_server.db import LOCAL_LEARNER, NotFound, new_id
from pupil_server.db.learning import AlreadyAnswered, AttemptRepo, QuizRepo
from pupil_server.learning.quiz import (
    QuestionResult,
    Quiz,
    QuizAttempt,
    QuizView,
    Response,
    learner_view,
)

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])

# One learner until remote mode adds accounts.
LEARNER = LOCAL_LEARNER


class ResultOut(BaseModel):
    question_id: str
    correct: bool
    response: Response | None
    """What the learner answered; None if they skipped it."""
    explanation: str | None


class AttemptOut(BaseModel):
    attempt_id: str
    correct: int
    total: int
    results: list[ResultOut]


class QuizOut(BaseModel):
    quiz: QuizView
    attempt: AttemptOut | None
    """The learner's answers and results, once they have taken it."""


class AnswersIn(BaseModel):
    responses: dict[str, Response]
    """Question id to answer; skipped questions are left out and count as wrong."""


def _attempt_out(quiz: Quiz, attempt: QuizAttempt, results: list[QuestionResult]) -> AttemptOut:
    explanations = {q.id: q.explanation for q in quiz.questions}
    return AttemptOut(
        attempt_id=attempt.id,
        correct=sum(r.correct for r in results),
        total=len(results),
        results=[
            ResultOut(
                question_id=r.question_id,
                correct=r.correct,
                response=attempt.responses.get(r.question_id),
                explanation=explanations[r.question_id],
            )
            for r in results
        ],
    )


@router.get("/{quiz_id}")
async def get_quiz(quiz_id: str, request: Request) -> QuizOut:
    db = request.app.state.db
    attempts = AttemptRepo(db)
    try:
        quiz = await QuizRepo(db).get(LEARNER, quiz_id)
        taken = await attempts.for_quiz(LEARNER, quiz_id)
    except NotFound:
        raise HTTPException(404, "no such quiz") from None
    attempt = None
    if taken:
        results = await attempts.results(LEARNER, taken.id)
        attempt = _attempt_out(quiz, taken, results)
    return QuizOut(quiz=learner_view(quiz), attempt=attempt)


@router.post("/{quiz_id}/attempts", status_code=201)
async def submit_answers(quiz_id: str, body: AnswersIn, request: Request) -> AttemptOut:
    db = request.app.state.db
    attempts = AttemptRepo(db)
    try:
        quiz = await QuizRepo(db).get(LEARNER, quiz_id)
        attempt = QuizAttempt(
            id=new_id("att"),
            quiz_id=quiz_id,
            responses=body.responses,
            submitted_at=datetime.now(UTC),
        )
        results = await attempts.submit(LEARNER, attempt)
    except NotFound:
        raise HTTPException(404, "no such quiz") from None
    except AlreadyAnswered:
        raise HTTPException(409, "this quiz has already been answered") from None
    except (ValueError, TypeError) as exc:
        # Answers to questions the quiz doesn't have, or of the wrong kind.
        raise HTTPException(422, str(exc)) from None
    return _attempt_out(quiz, attempt, results)
