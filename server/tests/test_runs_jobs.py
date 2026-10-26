import pytest

from pupil_server.runs.jobs import next_job


@pytest.mark.parametrize(
    ("level", "has_syllabus", "lessons", "untaken", "stops_left", "job"),
    [
        ("basics", False, 0, 0, False, "placement"),
        ("new", False, 0, 0, False, "plan"),  # nothing to place
        ("basics", False, 1, 1, False, None),  # placement waiting to be taken
        ("basics", False, 1, 0, False, "plan"),  # placement taken
        ("basics", True, 2, 1, True, "next_lesson"),  # one waiting: write one more
        ("basics", True, 3, 2, True, None),  # far enough ahead
        ("basics", True, 3, 0, True, "next_lesson"),
        ("basics", True, 3, 1, False, None),  # every stop has a lesson
    ],
    ids=[
        "start",
        "start-new-to-it",
        "placement-waiting",
        "placement-taken",
        "one-ahead",
        "two-ahead",
        "caught-up",
        "path-written",
    ],
)
def test_next_job(level, has_syllabus, lessons, untaken, stops_left, job):
    assert next_job(level, has_syllabus, lessons, untaken, stops_left) == job
