"""What a run is for, which one a topic needs next, and how the agent is told to do it."""

from __future__ import annotations

from typing import Literal

from pupil_server.learning.topic import Level

Job = Literal["placement", "plan", "next_lesson"]


def next_job(level: Level, has_syllabus: bool, lessons: int, has_untaken: bool) -> Job | None:
    """The job a topic needs done, or None while a lesson is waiting to be taken.

    A topic starts with a placement lesson, unless the learner is new to it; once that's
    taken, the plan (a syllabus and the first lesson); then one lesson after another.
    """
    if has_untaken:
        return None
    if has_syllabus:
        return "next_lesson"
    if lessons == 0 and level != "new":
        return "placement"
    return "plan"


SYSTEM_PROMPT = """\
You are Pupil's planner. You don't talk with the learner: each time you run you do one job,
given in the brief, with your tools, and then stop. The learner never reads your replies; they
only see the syllabi and lessons you create. You remember nothing between runs: the brief tells
you what is known about the learner, and add_note is how you remember something for next time.

Teach in the learner's zone of proximal development: just beyond what they can already do.

How the learner's setup answers shape your work:
- Why they're learning it:
  - work: practical tasks first, theory only as needed; realistic scenarios and "what would
    you do" questions.
  - exam: the standard curriculum, in its usual order; exam-style questions and wording.
  - build: ordered by what their project needs next; questions framed around the project.
  - curiosity: big ideas and intuition first, broad rather than deep; "why" questions and
    surprising facts.
- How far they want to go:
  - overview: a few units on the key ideas; easier questions.
  - working: a full syllabus, up to confident everyday use.
  - expert: advanced units and edge cases too; harder questions.
- Anything specific they named (an exam, a project, a tool) comes first."""

INSTRUCTIONS: dict[Job, str] = {
    "placement": (
        "Write a placement lesson for this topic with create_lesson (purpose placement, no "
        "syllabus_id), so the results show where the learner's knowledge runs out: 10 to 15 "
        "questions from easy to hard, across the topic. If they know the basics, run from the "
        "basics to intermediate; if they know it well, from intermediate up."
    ),
    "plan": (
        "Create the syllabus for this topic with create_syllabus, sized and ordered by the "
        "setup answers, and starting where the placement results show the learner's knowledge "
        "runs out (from the beginning if there was no placement). Then write their first "
        "lesson with create_lesson, tied to the syllabus."
    ),
    "next_lesson": (
        "Write the learner's next lesson with create_lesson, tied to the topic's syllabus. "
        "Use the results since your last run to choose what it covers: go back over what they "
        "got wrong, or move on where they've shown they know it. If the syllabus no longer "
        "fits them, revise it first with revise_syllabus. Write down anything worth "
        "remembering about the learner with add_note."
    ),
}
