"""Running the agent's jobs for topics, in the background.

A topic's lessons are written ahead of the learner, a stop on the path at a time: a run
writes one, and once it has, the next run starts if the topic needs another. A run is a fresh
agent session: it gets a brief built from the database, does its one job with its tools, and
ends. Nothing carries over between runs except what the database holds.

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
from pupil_server.db import Database
from pupil_server.db.runs import RunRepo
from pupil_server.learning.tools import learning_tools
from pupil_server.runs.brief import build_brief
from pupil_server.runs.jobs import SYSTEM_PROMPT, Job
from pupil_server.runs.log import UserMessage
from pupil_server.runs.state import TopicState, topic_state

log = logging.getLogger(__name__)


class RunGoing(RuntimeError):
    """The topic already has a run going."""


class NotFinished(RuntimeError):
    """The topic's path isn't finished, so there's nothing to go further from."""


class Runs:
    def __init__(
        self,
        db: Database,
        backend: AgentBackend,
        model: str | None = None,
        effort: str | None = None,
        max_turns: int = 24,
    ) -> None:
        self._db = db
        self._backend = backend
        self._model = model
        self._effort = effort
        self._max_turns = max_turns
        self._runs = RunRepo(db)
        self._tasks: dict[str, asyncio.Task[bool]] = {}
        self._jobs: dict[str, Job] = {}
        self._follow_ups: set[asyncio.Task[bool]] = set()
        self._closed = False

    def is_running(self, topic_id: str) -> bool:
        return topic_id in self._tasks

    def running_job(self, topic_id: str) -> Job | None:
        """The job of the topic's run that is going, if any. Known from the moment the run is
        started, before its record is written."""
        return self._jobs.get(topic_id)

    async def prepare(self, learner_id: str, topic_id: str) -> bool:
        """Start the run the topic needs next, unless one is going or none is needed.

        Returns whether a run is going afterwards. Never starts a second run for a topic.
        """
        if self._closed:
            return False
        if self.is_running(topic_id):
            return True
        state = await topic_state(self._db, learner_id, topic_id)
        if self.is_running(topic_id):  # started while we looked
            return True
        job = state.next_job
        if job is None:
            return False
        self._start(learner_id, state, job)
        return True

    async def extend(self, learner_id: str, topic_id: str) -> None:
        """Start a run that adds to a finished topic's path, as the learner asked."""
        if self.is_running(topic_id):
            raise RunGoing(topic_id)
        state = await topic_state(self._db, learner_id, topic_id)
        if self.is_running(topic_id):
            raise RunGoing(topic_id)
        if not state.finished:
            raise NotFinished(topic_id)
        self._start(learner_id, state, "extend")

    async def wait(self, topic_id: str) -> None:
        """Until the topic's runs have ended, including the ones each starts after it."""
        while True:
            if task := self._tasks.get(topic_id):
                await asyncio.wait([task])
            elif self._follow_ups:
                await asyncio.wait(list(self._follow_ups))
            else:
                return

    async def close(self) -> None:
        """Stop any runs still going; each records that it was cut off."""
        self._closed = True
        await asyncio.gather(*self._follow_ups, return_exceptions=True)
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _start(self, learner_id: str, state: TopicState, job: Job) -> None:
        topic_id = state.topic.id
        task = asyncio.create_task(self._run(learner_id, state, job))
        self._tasks[topic_id] = task
        self._jobs[topic_id] = job

        def done(_: asyncio.Task[bool]) -> None:
            del self._tasks[topic_id], self._jobs[topic_id]
            # Once a run has done its job, the topic may need another, e.g. to keep a lesson
            # ahead. Not after a failure, which would only fail again.
            if not self._closed and not task.cancelled() and task.result():
                follow_up = asyncio.create_task(self.prepare(learner_id, topic_id))
                self._follow_ups.add(follow_up)
                follow_up.add_done_callback(self._follow_ups.discard)

        task.add_done_callback(done)

    async def _run(self, learner_id: str, before: TopicState, job: Job) -> bool:
        """Do the job; whether the run did it."""
        topic = before.topic
        last = await self._runs.latest_success(learner_id, topic.id)
        run = await self._runs.start(learner_id, topic.id, job)
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
                self._db,
                learner_id,
                topic,
                job,
                last.started_at if last else None,
                before.next_stop,
            )
            await self._runs.append(learner_id, run.id, UserMessage(text=brief))
            config = AgentConfig(
                system_prompt=SYSTEM_PROMPT,
                tools=learning_tools(self._db, learner_id, topic.id),
                model=self._model,
                effort=self._effort,
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
                after = await topic_state(self._db, learner_id, topic.id)
                error = _missing(job, before, after)
            ended = True
        except Exception as exc:
            log.exception("run %s (%s) for topic %s failed", run.id, job, topic.id)
            error = f"{type(exc).__name__}: {exc}"
            ended = True
        finally:
            # Also when the run is cancelled, e.g. at shutdown: record how it ended.
            with anyio.CancelScope(shield=True):
                await save_text()
                if not ended:
                    error = "the run was cut off"
                await self._runs.finish(learner_id, run.id, error, cost)
        return error is None


def _missing(job: Job, before: TopicState, after: TopicState) -> str | None:
    """What the run should have made but didn't, if anything."""
    if job == "extend":
        return None if after.next_stop is not None else "the run didn't add to the path"
    if job == "plan" and after.syllabus is None:
        return "the run didn't create a syllabus"
    if len(after.lessons) <= len(before.lessons):
        return "the run didn't write a lesson"
    return None
