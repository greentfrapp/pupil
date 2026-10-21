"""Running the agent's jobs for topics, in the background.

Whenever a topic has no lesson waiting to be taken, a run prepares what it needs next. A run
is a fresh agent session: it gets a brief built from the database, does its one job with its
tools, and ends. Nothing carries over between runs except what the database holds.

At most one run per topic goes at a time. Pupil is a single server process, so an in-memory
marker per topic is enough.
"""

from __future__ import annotations

import asyncio
import logging

import anyio

from pupil_server.agents.base import (
    AgentBackend,
    AgentConfig,
    AgentError,
    TextDelta,
    TurnComplete,
)
from pupil_server.conversations.transcript import UserMessage
from pupil_server.db import Database
from pupil_server.db.learning import AttemptRepo, LessonRepo, SyllabusRepo
from pupil_server.db.runs import RunRepo
from pupil_server.db.topics import TopicRepo
from pupil_server.learning.tools import learning_tools
from pupil_server.runs.brief import build_brief
from pupil_server.runs.jobs import SYSTEM_PROMPT, Job, next_job

log = logging.getLogger(__name__)


class Runs:
    def __init__(self, db: Database, backend: AgentBackend, max_turns: int = 24) -> None:
        self._db = db
        self._backend = backend
        self._max_turns = max_turns
        self._runs = RunRepo(db)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._jobs: dict[str, Job] = {}

    def is_running(self, topic_id: str) -> bool:
        return topic_id in self._tasks

    def running_job(self, topic_id: str) -> Job | None:
        """The job of the topic's run that is going, if any. Known from the moment the run is
        started, before its record is written."""
        return self._jobs.get(topic_id)

    async def prepare(self, learner_id: str, topic_id: str) -> bool:
        """Start the run the topic needs next, unless one is going or a lesson is waiting.

        Returns whether a run is going afterwards. Never starts a second run for a topic.
        """
        if self.is_running(topic_id):
            return True
        job = await self.next_job(learner_id, topic_id)
        if self.is_running(topic_id):  # started while we looked
            return True
        if job is None:
            return False
        task = asyncio.create_task(self._run(learner_id, topic_id, job))
        self._tasks[topic_id] = task
        self._jobs[topic_id] = job

        def done(_: asyncio.Task[None]) -> None:
            del self._tasks[topic_id], self._jobs[topic_id]

        task.add_done_callback(done)
        return True

    async def wait(self, topic_id: str) -> None:
        """Until the topic's run, if one is going, has ended."""
        task = self._tasks.get(topic_id)
        if task is not None:
            await asyncio.wait([task])

    async def next_job(self, learner_id: str, topic_id: str) -> Job | None:
        topic = await TopicRepo(self._db).get(learner_id, topic_id)
        syllabus = await SyllabusRepo(self._db).for_topic(learner_id, topic_id)
        lessons = await LessonRepo(self._db).for_topic(learner_id, topic_id)
        attempts = AttemptRepo(self._db)
        untaken = [
            lesson for lesson in lessons if not await attempts.for_lesson(learner_id, lesson.id)
        ]
        return next_job(topic.profile.level, syllabus is not None, len(lessons), bool(untaken))

    async def close(self) -> None:
        """Stop any runs still going; each records that it was cut off."""
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, learner_id: str, topic_id: str, job: Job) -> None:
        topic = await TopicRepo(self._db).get(learner_id, topic_id)
        last = await self._runs.latest_success(learner_id, topic_id)
        run = await self._runs.start(learner_id, topic_id, job)
        error: str | None = None
        cost: float | None = None
        ended = False
        text: list[str] = []

        async def save_text() -> None:
            if text:
                merged = TextDelta(text="".join(text))
                text.clear()
                await self._runs.append(learner_id, run.id, merged)

        try:
            brief = await build_brief(
                self._db, learner_id, topic, job, last.started_at if last else None
            )
            await self._runs.append(learner_id, run.id, UserMessage(text=brief))
            config = AgentConfig(
                system_prompt=SYSTEM_PROMPT,
                tools=learning_tools(self._db, learner_id, topic_id),
                max_turns=self._max_turns,
            )
            session = await self._backend.open_session(config)
            try:
                async for event in session.send(brief):
                    if isinstance(event, TextDelta):
                        text.append(event.text)
                        continue
                    await save_text()
                    await self._runs.append(learner_id, run.id, event)
                    if isinstance(event, TurnComplete):
                        cost = event.cost_usd
                    elif isinstance(event, AgentError):
                        error = event.message
            finally:
                await session.close()
            if error is None:
                error = await self._missing(learner_id, topic_id, job)
            ended = True
        except Exception as exc:
            log.exception("run %s (%s) for topic %s failed", run.id, job, topic_id)
            error = f"{type(exc).__name__}: {exc}"
            ended = True
        finally:
            # Also when the run is cancelled, e.g. at shutdown: record how it ended.
            with anyio.CancelScope(shield=True):
                await save_text()
                if not ended:
                    error = "the run was cut off"
                await self._runs.finish(learner_id, run.id, error, cost)

    async def _missing(self, learner_id: str, topic_id: str, job: Job) -> str | None:
        """What the run should have made but didn't, if anything."""
        if job == "plan" and await SyllabusRepo(self._db).for_topic(learner_id, topic_id) is None:
            return "the run didn't create a syllabus"
        if await self.next_job(learner_id, topic_id) is not None:
            return "the run didn't leave a lesson to take"
        return None
