"""Repositories for syllabi, quizzes and attempts, and the evidence attempts give.

Every method takes the learner it acts for, and only sees that learner's records: another
learner's id is simply not found.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from pupil_server.db.database import AlreadyExists, Database, NotFound, timestamp
from pupil_server.learning.progress import Evidence
from pupil_server.learning.quiz import QuestionResult, Quiz, QuizAttempt, grade_attempt
from pupil_server.learning.syllabus import Syllabus


class StaleRevision(ValueError):
    """A syllabus change was based on a revision that is no longer the latest."""


class AlreadyAnswered(ValueError):
    """The quiz has an attempt already; each quiz is answered once."""


class SyllabusRepo:
    """Each change to a syllabus is stored as a new revision; the latest is the current plan."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, learner_id: str, syllabus: Syllabus) -> Syllabus:
        """Store a new syllabus as revision 1, whatever revision it carries."""
        first = syllabus.model_copy(update={"revision": 1})

        def work(conn: sqlite3.Connection) -> Syllabus:
            if _latest_revision(conn, syllabus.id) is not None:
                raise AlreadyExists(f"syllabus {syllabus.id!r} already exists; revise it instead")
            _insert_syllabus(conn, learner_id, first)
            return first

        return await self._db.run(work)

    async def revise(self, learner_id: str, syllabus: Syllabus) -> Syllabus:
        """Store `syllabus` as the next revision.

        Its `revision` must be the one the change was based on, and that must still be the
        latest, so a change made from a stale copy can't silently undo a newer one.
        """

        def work(conn: sqlite3.Connection) -> Syllabus:
            latest = _latest_syllabus(conn, learner_id, syllabus.id)
            if syllabus.revision != latest.revision:
                raise StaleRevision(
                    f"syllabus {syllabus.id!r} is at revision {latest.revision}, but this change "
                    f"is based on revision {syllabus.revision}"
                )
            revised = syllabus.model_copy(update={"revision": latest.revision + 1})
            _insert_syllabus(conn, learner_id, revised)
            return revised

        return await self._db.run(work)

    async def get(self, learner_id: str, syllabus_id: str, revision: int | None = None) -> Syllabus:
        """The latest revision, or the one asked for."""

        def work(conn: sqlite3.Connection) -> Syllabus:
            if revision is None:
                return _latest_syllabus(conn, learner_id, syllabus_id)
            row = conn.execute(
                "SELECT body FROM syllabi WHERE learner_id = ? AND id = ? AND revision = ?",
                (learner_id, syllabus_id, revision),
            ).fetchone()
            if row is None:
                raise NotFound(f"no revision {revision} of syllabus {syllabus_id!r}")
            return Syllabus.model_validate_json(row["body"])

        return await self._db.run(work)

    async def list_latest(self, learner_id: str) -> list[Syllabus]:
        """The learner's syllabi at their latest revisions, oldest syllabus first."""

        def work(conn: sqlite3.Connection) -> list[Syllabus]:
            rows = conn.execute(
                """
                SELECT body FROM syllabi AS s
                WHERE learner_id = ?
                  AND revision = (SELECT max(revision) FROM syllabi WHERE id = s.id)
                ORDER BY (SELECT min(created_at) FROM syllabi WHERE id = s.id), id
                """,
                (learner_id,),
            )
            return [Syllabus.model_validate_json(r["body"]) for r in rows]

        return await self._db.run(work)


class QuizRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, learner_id: str, quiz: Quiz) -> None:
        """Store a quiz. One tied to a syllabus must tag only objectives its latest revision has."""

        def work(conn: sqlite3.Connection) -> None:
            if conn.execute("SELECT 1 FROM quizzes WHERE id = ?", (quiz.id,)).fetchone():
                raise AlreadyExists(f"quiz {quiz.id!r} already exists")
            if quiz.syllabus_id is not None:
                quiz.check_tags(_latest_syllabus(conn, learner_id, quiz.syllabus_id))
            conn.execute(
                "INSERT INTO quizzes (id, learner_id, syllabus_id, body, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (quiz.id, learner_id, quiz.syllabus_id, quiz.model_dump_json(), _now()),
            )

        await self._db.run(work)

    async def get(self, learner_id: str, quiz_id: str) -> Quiz:
        return await self._db.run(lambda conn: _quiz(conn, learner_id, quiz_id))


class AttemptRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def submit(self, learner_id: str, attempt: QuizAttempt) -> list[QuestionResult]:
        """Grade an attempt and store it with its results, all or nothing.

        A quiz is answered once, so a second attempt at it is refused. For a quiz tied to a
        syllabus, each result also becomes evidence for every objective its question tests.
        """

        def work(conn: sqlite3.Connection) -> list[QuestionResult]:
            quiz = _quiz(conn, learner_id, attempt.quiz_id)
            if conn.execute("SELECT 1 FROM attempts WHERE id = ?", (attempt.id,)).fetchone():
                raise AlreadyExists(f"attempt {attempt.id!r} already exists")
            # Checked in the same transaction as the insert, so two submissions can't both pass.
            if conn.execute("SELECT 1 FROM attempts WHERE quiz_id = ?", (quiz.id,)).fetchone():
                raise AlreadyAnswered(f"quiz {quiz.id!r} has already been answered")
            results = grade_attempt(quiz, attempt)
            at = timestamp(attempt.submitted_at)
            conn.execute(
                "INSERT INTO attempts (id, learner_id, quiz_id, body, submitted_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (attempt.id, learner_id, quiz.id, attempt.model_dump_json(), at),
            )
            conn.executemany(
                "INSERT INTO question_results (attempt_id, question_id, correct) VALUES (?, ?, ?)",
                [(attempt.id, r.question_id, r.correct) for r in results],
            )
            if quiz.syllabus_id is not None:
                conn.executemany(
                    "INSERT INTO evidence (learner_id, syllabus_id, objective_id, attempt_id, "
                    "question_id, correct, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (learner_id, quiz.syllabus_id, o, attempt.id, r.question_id, r.correct, at)
                        for r in results
                        for o in r.objective_ids
                    ],
                )
            return results

        return await self._db.run(work)

    async def get(self, learner_id: str, attempt_id: str) -> QuizAttempt:
        def work(conn: sqlite3.Connection) -> QuizAttempt:
            return QuizAttempt.model_validate_json(
                _attempt_row(conn, learner_id, attempt_id)["body"]
            )

        return await self._db.run(work)

    async def results(self, learner_id: str, attempt_id: str) -> list[QuestionResult]:
        """The stored results, in quiz order."""

        def work(conn: sqlite3.Connection) -> list[QuestionResult]:
            quiz = _quiz(conn, learner_id, _attempt_row(conn, learner_id, attempt_id)["quiz_id"])
            correct = dict(
                conn.execute(
                    "SELECT question_id, correct FROM question_results WHERE attempt_id = ?",
                    (attempt_id,),
                ).fetchall()
            )
            return [
                QuestionResult(
                    question_id=q.id, correct=correct[q.id], objective_ids=q.objective_ids
                )
                for q in quiz.questions
            ]

        return await self._db.run(work)

    async def for_quiz(self, learner_id: str, quiz_id: str) -> QuizAttempt | None:
        """The learner's attempt at the quiz, or None if they haven't answered it yet."""

        def work(conn: sqlite3.Connection) -> QuizAttempt | None:
            _quiz(conn, learner_id, quiz_id)
            row = conn.execute(
                "SELECT body FROM attempts WHERE learner_id = ? AND quiz_id = ?",
                (learner_id, quiz_id),
            ).fetchone()
            return QuizAttempt.model_validate_json(row["body"]) if row else None

        return await self._db.run(work)


class EvidenceRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def for_syllabus(self, learner_id: str, syllabus_id: str) -> list[Evidence]:
        """Everything the learner's attempts showed about the syllabus's objectives, oldest first."""

        def work(conn: sqlite3.Connection) -> list[Evidence]:
            rows = conn.execute(
                "SELECT objective_id, attempt_id, question_id, correct, at FROM evidence "
                "WHERE learner_id = ? AND syllabus_id = ? ORDER BY at, rowid",
                (learner_id, syllabus_id),
            )
            return [Evidence.model_validate(dict(r)) for r in rows]

        return await self._db.run(work)


def _now() -> str:
    return timestamp(datetime.now(UTC))


def _latest_revision(conn: sqlite3.Connection, syllabus_id: str) -> int | None:
    row = conn.execute("SELECT max(revision) FROM syllabi WHERE id = ?", (syllabus_id,)).fetchone()
    return row[0]


def _latest_syllabus(conn: sqlite3.Connection, learner_id: str, syllabus_id: str) -> Syllabus:
    row = conn.execute(
        "SELECT body FROM syllabi WHERE learner_id = ? AND id = ? ORDER BY revision DESC LIMIT 1",
        (learner_id, syllabus_id),
    ).fetchone()
    if row is None:
        raise NotFound(f"no syllabus {syllabus_id!r}")
    return Syllabus.model_validate_json(row["body"])


def _insert_syllabus(conn: sqlite3.Connection, learner_id: str, syllabus: Syllabus) -> None:
    conn.execute(
        "INSERT INTO syllabi (id, revision, learner_id, body, created_at) VALUES (?, ?, ?, ?, ?)",
        (syllabus.id, syllabus.revision, learner_id, syllabus.model_dump_json(), _now()),
    )


def _quiz(conn: sqlite3.Connection, learner_id: str, quiz_id: str) -> Quiz:
    row = conn.execute(
        "SELECT body FROM quizzes WHERE learner_id = ? AND id = ?", (learner_id, quiz_id)
    ).fetchone()
    if row is None:
        raise NotFound(f"no quiz {quiz_id!r}")
    return Quiz.model_validate_json(row["body"])


def _attempt_row(conn: sqlite3.Connection, learner_id: str, attempt_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT quiz_id, body FROM attempts WHERE learner_id = ? AND id = ?",
        (learner_id, attempt_id),
    ).fetchone()
    if row is None:
        raise NotFound(f"no attempt {attempt_id!r}")
    return row
