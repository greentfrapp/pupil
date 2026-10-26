-- Learners; the topics they asked to learn, with what was made for each (syllabi, lessons,
-- attempts and what they show); and the agent's runs for each topic. Every table is
-- append-only. Timestamps are ISO 8601 UTC text.

CREATE TABLE learners (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE topics (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (id),
    request TEXT NOT NULL, -- what the learner typed
    profile TEXT NOT NULL, -- Profile JSON: the answers to the setup questions
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX topics_by_learner ON topics (learner_id, created_at);

-- Each revision of a syllabus is a new row; the latest revision is the current plan.
CREATE TABLE syllabi (
    id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    learner_id TEXT NOT NULL REFERENCES learners (id),
    topic_id TEXT NOT NULL REFERENCES topics (id),
    body TEXT NOT NULL, -- Syllabus JSON
    created_at TEXT NOT NULL,
    PRIMARY KEY (id, revision)
) STRICT;

CREATE INDEX syllabi_by_learner ON syllabi (learner_id, id);
CREATE INDEX syllabi_by_topic ON syllabi (topic_id, created_at);

CREATE TABLE lessons (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (id),
    topic_id TEXT NOT NULL REFERENCES topics (id),
    syllabus_id TEXT, -- NULL for a placement lesson written before any syllabus
    body TEXT NOT NULL, -- Lesson JSON
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX lessons_by_topic ON lessons (topic_id, created_at);

-- A lesson can be retried, so it can have many attempts, numbered from 1.
CREATE TABLE attempts (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (id),
    lesson_id TEXT NOT NULL REFERENCES lessons (id),
    number INTEGER NOT NULL CHECK (number >= 1),
    body TEXT NOT NULL, -- Attempt JSON, holding the learner's responses
    submitted_at TEXT NOT NULL,
    UNIQUE (lesson_id, number)
) STRICT;

CREATE INDEX attempts_by_learner ON attempts (learner_id, submitted_at);

-- How each question of an attempt was graded, including untagged placement questions.
CREATE TABLE question_results (
    attempt_id TEXT NOT NULL REFERENCES attempts (id),
    question_id TEXT NOT NULL,
    correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
    PRIMARY KEY (attempt_id, question_id)
) STRICT;

-- One row per objective a graded question tests, for lessons tied to a syllabus.
CREATE TABLE evidence (
    learner_id TEXT NOT NULL REFERENCES learners (id),
    syllabus_id TEXT NOT NULL,
    objective_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL, -- 1 for a first attempt; retries test recall of answers shown
    question_id TEXT NOT NULL,
    correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
    at TEXT NOT NULL,
    PRIMARY KEY (attempt_id, question_id, objective_id),
    FOREIGN KEY (attempt_id, question_id) REFERENCES question_results (attempt_id, question_id)
) STRICT;

CREATE INDEX evidence_by_syllabus ON evidence (learner_id, syllabus_id, at);

-- What the agent wrote down about the learner, to remember in later runs.
CREATE TABLE notes (
    topic_id TEXT NOT NULL REFERENCES topics (id),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX notes_by_topic ON notes (topic_id, created_at);

-- The agent's one-off jobs for a topic, e.g. writing its next lesson.
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (id),
    topic_id TEXT NOT NULL REFERENCES topics (id),
    job TEXT NOT NULL, -- e.g. placement, plan, next_lesson
    started_at TEXT NOT NULL
) STRICT;

CREATE INDEX runs_by_topic ON runs (topic_id, started_at);

-- How a run ended, written when it does. A run without one was cut off, e.g. by a restart.
CREATE TABLE run_ends (
    run_id TEXT PRIMARY KEY REFERENCES runs (id),
    finished_at TEXT NOT NULL,
    error TEXT, -- NULL when the run did its job
    cost_usd REAL
) STRICT;

-- The run's brief and the agent's events.
CREATE TABLE run_items (
    run_id TEXT NOT NULL REFERENCES runs (id),
    seq INTEGER NOT NULL,
    at TEXT NOT NULL,
    body TEXT NOT NULL, -- LogItem JSON
    PRIMARY KEY (run_id, seq)
) STRICT;
