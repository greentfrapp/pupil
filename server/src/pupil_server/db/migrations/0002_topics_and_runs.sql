-- Topics: what the learner asked to learn, with everything made for it pointing back at it.
-- Runs: the agent's one-off jobs for a topic, and their logs. Append-only, like the rest.

CREATE TABLE topics (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (id),
    request TEXT NOT NULL, -- what the learner typed
    profile TEXT NOT NULL, -- Profile JSON: the answers to the setup questions
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX topics_by_learner ON topics (learner_id, created_at);

-- NULL for syllabi and lessons made outside a topic, e.g. by the chat.
ALTER TABLE syllabi ADD COLUMN topic_id TEXT REFERENCES topics (id);
ALTER TABLE lessons ADD COLUMN topic_id TEXT REFERENCES topics (id);

CREATE INDEX syllabi_by_topic ON syllabi (topic_id, created_at);
CREATE INDEX lessons_by_topic ON lessons (topic_id, created_at);

-- What the agent wrote down about the learner, to remember in later runs.
CREATE TABLE notes (
    topic_id TEXT NOT NULL REFERENCES topics (id),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX notes_by_topic ON notes (topic_id, created_at);

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

-- The run's brief and the agent's events, as conversations store theirs.
CREATE TABLE run_items (
    run_id TEXT NOT NULL REFERENCES runs (id),
    seq INTEGER NOT NULL,
    at TEXT NOT NULL,
    body TEXT NOT NULL, -- TranscriptItem JSON
    PRIMARY KEY (run_id, seq)
) STRICT;
