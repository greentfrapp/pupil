"""The brief a run starts from: its job, and what is known about the learner and the topic.

The agent remembers nothing between runs, so the brief must hold what every run needs. It is
kept bounded; details needed only sometimes are left to the read tools.
"""

from __future__ import annotations

from datetime import datetime

from pupil_server.db import Database
from pupil_server.db.learning import AttemptRepo, LessonRepo, SyllabusRepo
from pupil_server.db.topics import TopicRepo
from pupil_server.learning.lesson import describe_attempt
from pupil_server.learning.topic import Topic
from pupil_server.runs.jobs import INSTRUCTIONS, Job

RECENT_LESSONS = 10
"""How many of the newest lessons the brief lists."""
MAX_RESULTS = 20
"""At most this many attempts since the last run are described, the newest."""

WHY = {
    "work": "for work",
    "exam": "for a course or exam",
    "build": "to build something",
    "curiosity": "out of curiosity",
}
DEPTH = {
    "overview": "a quick overview",
    "working": "solid working knowledge",
    "expert": "deep expertise",
}
LEVEL = {"new": "new to this", "basics": "knows the basics", "well": "knows it well"}


async def build_brief(
    db: Database, learner_id: str, topic: Topic, job: Job, since: datetime | None
) -> str:
    """The brief for a run doing `job`, with the results of attempts made after `since`."""
    profile = topic.profile
    sections = [
        f"# Your job\n{INSTRUCTIONS[job]}",
        "\n".join(
            [
                f"# The topic\nThe learner asked to learn: {topic.request!r}",
                f"- Why: {WHY[profile.why]} ({profile.why})",
                f"- How far: {DEPTH[profile.depth]} ({profile.depth})",
                f"- Knows already: {LEVEL[profile.level]} ({profile.level})",
                f"- Anything specific: {profile.specific or 'nothing'}",
            ]
        ),
    ]

    notes = await TopicRepo(db).notes(learner_id, topic.id)
    sections.append("# Your notes\n" + ("\n".join(f"- {n.text}" for n in notes) or "None yet."))

    syllabus = await SyllabusRepo(db).for_topic(learner_id, topic.id)
    sections.append(
        "# The syllabus\n"
        + ("None yet." if syllabus is None else syllabus.model_dump_json(indent=2))
    )

    lessons = LessonRepo(db)
    attempts = AttemptRepo(db)
    results = (await attempts.since(learner_id, topic.id, since))[-MAX_RESULTS:]
    described = [
        describe_attempt(await lessons.get(learner_id, g.attempt.lesson_id), g) for g in results
    ]
    sections.append("# Results since your last run\n" + ("\n\n".join(described) or "None."))

    lines = []
    for lesson in (await lessons.for_topic(learner_id, topic.id))[-RECENT_LESSONS:]:
        taken = await attempts.for_lesson(learner_id, lesson.id)
        if taken:
            times = "once" if len(taken) == 1 else f"{len(taken)} times"
            latest = taken[-1]
            summary = f"taken {times}, latest {latest.correct} of {len(latest.results)} right"
        else:
            summary = "not taken yet"
        lines.append(
            f"- {lesson.title!r} ({lesson.id}, {lesson.purpose}, "
            f"{len(lesson.questions)} questions): {summary}"
        )
    sections.append("# Recent lessons, oldest first\n" + ("\n".join(lines) or "None yet."))
    return "\n\n".join(sections)
