"""What a run is for, which one a topic needs next, and how the agent is told to do it."""

from __future__ import annotations

from typing import Literal

from pupil_server.learning.topic import Level

Job = Literal["placement", "plan", "next_lesson", "extend"]

AHEAD = 2
"""How many lessons are kept written but untaken: the next one, and one more written while
the learner takes it. A run takes less time than a lesson, so the learner never waits, and
each lesson is written knowing the results of all but the one being taken."""


def next_job(
    level: Level, has_syllabus: bool, lessons: int, untaken: int, stops_left: bool
) -> Job | None:
    """The job a topic needs done, or None when nothing is needed yet.

    A topic starts with a placement lesson, unless the learner is new to it; once that's
    taken, the plan (a syllabus and its first lesson); then a lesson for each stop on the
    path, kept `AHEAD` of the learner. Going further than the path is the learner's choice
    (`extend`), so never needed here.
    """
    if not has_syllabus:
        if untaken:
            return None
        return "placement" if lessons == 0 and level != "new" else "plan"
    if untaken >= AHEAD or not stops_left:
        return None
    return "next_lesson"


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
- Anything specific they named (an exam, a project, a tool) comes first.

# Checking facts
The learner trusts every answer key, so a wrong one does real harm. Before you use a fact,
name, date, number, order or quote you aren't sure of, look it up with web search, preferring
primary or authoritative sources. If a check changes what you were going to write, use what
you found; if you can't confirm something, leave it out. Don't search for what you know well:
checks are for the details models get wrong, such as names, dates, orders, quotes and who did
what."""

INSTRUCTIONS: dict[Job, str] = {
    "placement": (
        "Write a placement lesson for this topic with create_lesson (purpose placement, no "
        "syllabus_id), so the results show where the learner's knowledge runs out: 10 to 15 "
        "questions from easy to hard, across the topic. If they know the basics, run from the "
        "basics to intermediate; if they know it well, from intermediate up."
    ),
    "plan": (
        "Before planning, search to scope the topic: its core ideas, the usual order to "
        "learn them in, and common misconceptions. "
        "Create the syllabus for this topic with create_syllabus, sized and ordered by the "
        "setup answers, and starting where the placement results show the learner's knowledge "
        "runs out (from the beginning if there was no placement). Give each unit the number "
        "of lessons it needs: together they are the learner's whole path, and the topic ends "
        "when they've taken them all. The learner sees the plan next, with its rationale: say "
        "in one plain line how their answers and placement shaped it. Then write the first "
        "lesson of the first unit with create_lesson."
    ),
    "next_lesson": (
        "Write the lesson for the stop on the path given below, with create_lesson. Use the "
        "results since your last run to choose what it covers: go back over what they got "
        "wrong, or move on where they've shown they know it. The learner may still be taking "
        "the lesson before it, so those results can be missing. A unit's last lesson also "
        "rounds it off: cover anything in the unit they haven't yet got right. If the "
        "syllabus no longer fits them, revise it first with revise_syllabus."
    ),
    "extend": (
        "The learner has taken every lesson on their path and wants to go further. Search "
        "first to see what lies deeper or wider than the syllabus so far. Add new "
        "units with revise_syllabus that go deeper or wider than the syllabus so far, each "
        "with its number of lessons, and update the rationale to say what the new units add. "
        "Keep the existing units as they are. Don't write lessons: they are written next."
    ),
}
