"""Repositories for syllabi, lessons and attempts, and the evidence attempts give.

Every method takes the learner it acts for, and only sees that learner's records: another
learner's id is simply not found.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from pupil_server.db.database import AlreadyExists, Database, NotFound, timestamp
from pupil_server.learning.lesson import (
    Attempt,
    GradedAttempt,
    Lesson,
    QuestionResult,
    check_attempt,
)
from pupil_server.learning.progress import Evidence
from pupil_server.learning.syllabus import Syllabus


class StaleRevision(ValueError):
    """A syllabus change was based on a revision that is no longer the latest."""


class PlacementTaken(ValueError):
    """A placement lesson is taken once; redoing placement means starting the topic again."""


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


class LessonRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, learner_id: str, lesson: Lesson) -> None:
        """Store a lesson. One tied to a syllabus must tag only objectives its latest revision
        has."""

        def work(conn: sqlite3.Connection) -> None:
            if conn.execute("SELECT 1 FROM lessons WHERE id = ?", (lesson.id,)).fetchone():
                raise AlreadyExists(f"lesson {lesson.id!r} already exists")
            if lesson.syllabus_id is not None:
                lesson.check_tags(_latest_syllabus(conn, learner_id, lesson.syllabus_id))
            conn.execute(
                "INSERT INTO lessons (id, learner_id, syllabus_id, body, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (lesson.id, learner_id, lesson.syllabus_id, lesson.model_dump_json(), _now()),
            )

        await self._db.run(work)

    async def get(self, learner_id: str, lesson_id: str) -> Lesson:
        return await self._db.run(lambda conn: _lesson(conn, learner_id, lesson_id))


class AttemptRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def submit(self, learner_id: str, attempt: Attempt) -> GradedAttempt:
        """Store an attempt graded by the lesson player, with its results, all or nothing.

        The attempt must fit the lesson; its grades are taken as given. Attempts at a lesson
        are numbered from 1; a placement lesson can't be retried. For a
        lesson tied to a syllabus, each result also becomes evidence for every objective its
        question tests.
        """

        def work(conn: sqlite3.Connection) -> GradedAttempt:
            lesson = _lesson(conn, learner_id, attempt.lesson_id)
            if conn.execute("SELECT 1 FROM attempts WHERE id = ?", (attempt.id,)).fetchone():
                raise AlreadyExists(f"attempt {attempt.id!r} already exists")
            results = check_attempt(lesson, attempt)
            # Counted in the same transaction as the insert, so two submissions can't share
            # a number.
            earlier = conn.execute(
                "SELECT count(*) FROM attempts WHERE lesson_id = ?", (lesson.id,)
            ).fetchone()[0]
            if lesson.purpose == "placement" and earlier:
                raise PlacementTaken(f"placement lesson {lesson.id!r} has already been taken")
            number = earlier + 1
            at = timestamp(attempt.submitted_at)
            conn.execute(
                "INSERT INTO attempts (id, learner_id, lesson_id, number, body, submitted_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (attempt.id, learner_id, lesson.id, number, attempt.model_dump_json(), at),
            )
            conn.executemany(
                "INSERT INTO question_results (attempt_id, question_id, correct) VALUES (?, ?, ?)",
                [(attempt.id, r.question_id, r.correct) for r in results],
            )
            if lesson.syllabus_id is not None:
                conn.executemany(
                    "INSERT INTO evidence (learner_id, syllabus_id, objective_id, attempt_id, "
                    "attempt_number, question_id, correct, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            learner_id,
                            lesson.syllabus_id,
                            o,
                            attempt.id,
                            number,
                            r.question_id,
                            r.correct,
                            at,
                        )
                        for r in results
                        for o in r.objective_ids
                    ],
                )
            return GradedAttempt(attempt=attempt, number=number, results=results)

        return await self._db.run(work)

    async def get(self, learner_id: str, attempt_id: str) -> GradedAttempt:
        def work(conn: sqlite3.Connection) -> GradedAttempt:
            row = conn.execute(
                f"{_ATTEMPTS} WHERE learner_id = ? AND id = ?", (learner_id, attempt_id)
            ).fetchone()
            if row is None:
                raise NotFound(f"no attempt {attempt_id!r}")
            return _graded(conn, learner_id, row)

        return await self._db.run(work)

    async def for_lesson(self, learner_id: str, lesson_id: str) -> list[GradedAttempt]:
        """The learner's attempts at the lesson, first attempt first."""

        def work(conn: sqlite3.Connection) -> list[GradedAttempt]:
            _lesson(conn, learner_id, lesson_id)
            rows = conn.execute(
                f"{_ATTEMPTS} WHERE learner_id = ? AND lesson_id = ? ORDER BY number",
                (learner_id, lesson_id),
            )
            return [_graded(conn, learner_id, r) for r in rows.fetchall()]

        return await self._db.run(work)

    async def recent(self, learner_id: str, limit: int) -> list[GradedAttempt]:
        """The learner's latest attempts at any lesson, newest first."""

        def work(conn: sqlite3.Connection) -> list[GradedAttempt]:
            rows = conn.execute(
                f"{_ATTEMPTS} WHERE learner_id = ? ORDER BY submitted_at DESC, rowid DESC LIMIT ?",
                (learner_id, limit),
            )
            return [_graded(conn, learner_id, r) for r in rows.fetchall()]

        return await self._db.run(work)


class EvidenceRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def for_syllabus(self, learner_id: str, syllabus_id: str) -> list[Evidence]:
        """Everything the learner's attempts showed about the syllabus's objectives, oldest first."""

        def work(conn: sqlite3.Connection) -> list[Evidence]:
            rows = conn.execute(
                "SELECT objective_id, attempt_id, attempt_number, question_id, correct, at "
                "FROM evidence "
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


def _lesson(conn: sqlite3.Connection, learner_id: str, lesson_id: str) -> Lesson:
    row = conn.execute(
        "SELECT body FROM lessons WHERE learner_id = ? AND id = ?", (learner_id, lesson_id)
    ).fetchone()
    if row is None:
        raise NotFound(f"no lesson {lesson_id!r}")
    return Lesson.model_validate_json(row["body"])


_ATTEMPTS = "SELECT id, lesson_id, number, body FROM attempts"


def _graded(conn: sqlite3.Connection, learner_id: str, row: sqlite3.Row) -> GradedAttempt:
    """An attempt row with its stored results, in lesson order."""
    lesson = _lesson(conn, learner_id, row["lesson_id"])
    correct = dict(
        conn.execute(
            "SELECT question_id, correct FROM question_results WHERE attempt_id = ?", (row["id"],)
        ).fetchall()
    )
    return GradedAttempt(
        attempt=Attempt.model_validate_json(row["body"]),
        number=row["number"],
        results=[
            QuestionResult(question_id=q.id, correct=correct[q.id], objective_ids=q.objective_ids)
            for q in lesson.questions
        ],
    )
