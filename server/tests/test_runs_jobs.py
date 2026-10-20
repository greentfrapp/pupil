import pytest

from pupil_server.runs.jobs import next_job


@pytest.mark.parametrize(
    ("level", "has_syllabus", "lessons", "has_untaken", "job"),
    [
        ("basics", False, 0, False, "placement"),
        ("new", False, 0, False, "plan"),  # nothing to place
        ("basics", False, 1, True, None),  # placement waiting to be taken
        ("basics", False, 1, False, "plan"),  # placement taken
        ("basics", True, 2, True, None),  # a lesson waiting to be taken
        ("basics", True, 2, False, "next_lesson"),
    ],
    ids=[
        "start",
        "start-new-to-it",
        "placement-waiting",
        "placement-taken",
        "lesson-waiting",
        "lesson-taken",
    ],
)
def test_next_job(level, has_syllabus, lessons, has_untaken, job):
    assert next_job(level, has_syllabus, lessons, has_untaken) == job
