"""Where a topic stands: its syllabus, its lessons as stops on the path, and what it needs."""

from __future__ import annotations

from dataclasses import dataclass

from pupil_server.db import Database
from pupil_server.db.learning import AttemptRepo, LessonRepo, SyllabusRepo
from pupil_server.db.topics import TopicRepo
from pupil_server.learning.lesson import Lesson
from pupil_server.learning.path import PathUnit, Stop, next_stop, path
from pupil_server.learning.syllabus import Syllabus
from pupil_server.learning.topic import Topic
from pupil_server.runs.jobs import Job, next_job


@dataclass(frozen=True)
class TopicState:
    topic: Topic
    syllabus: Syllabus | None
    lessons: list[Lesson]
    """Oldest first."""
    untaken: list[Lesson]
    """Lessons with no attempts yet, oldest first."""
    path: list[PathUnit]
    """Empty without a syllabus."""

    @property
    def next_stop(self) -> Stop | None:
        """The first stop without a lesson, if the topic has a path and one is left."""
        return next_stop(self.path)

    @property
    def finished(self) -> bool:
        """Every stop on the path has a lesson, and every lesson has been taken."""
        return self.syllabus is not None and self.next_stop is None and not self.untaken

    @property
    def next_job(self) -> Job | None:
        return next_job(
            self.topic.profile.level,
            self.syllabus is not None,
            len(self.lessons),
            len(self.untaken),
            self.next_stop is not None,
        )


async def topic_state(db: Database, learner_id: str, topic_id: str) -> TopicState:
    topic = await TopicRepo(db).get(learner_id, topic_id)
    syllabus = await SyllabusRepo(db).for_topic(learner_id, topic_id)
    lessons = await LessonRepo(db).for_topic(learner_id, topic_id)
    attempts = AttemptRepo(db)
    untaken = [lesson for lesson in lessons if not await attempts.for_lesson(learner_id, lesson.id)]
    return TopicState(
        topic=topic,
        syllabus=syllabus,
        lessons=lessons,
        untaken=untaken,
        path=path(syllabus, lessons) if syllabus else [],
    )
