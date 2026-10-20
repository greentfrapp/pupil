-- Learners, the learning records (syllabi, lessons, attempts and what they show), and
-- conversations with the tutor. Every table is append-only. Timestamps are ISO 8601 UTC text.

CREATE TABLE learners (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
) STRICT;

-- Each revision of a syllabus is a new row; the latest revision is the current plan.
CREATE TABLE syllabi (
    id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    learner_id TEXT NOT NULL REFERENCES learners (id),
    body TEXT NOT NULL, -- Syllabus JSON
    created_at TEXT NOT NULL,
    PRIMARY KEY (id, revision)
) STRICT;

CREATE INDEX syllabi_by_learner ON syllabi (learner_id, id);

CREATE TABLE lessons (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (id),
    syllabus_id TEXT, -- NULL for a placement lesson written before any syllabus
    body TEXT NOT NULL, -- Lesson JSON
    created_at TEXT NOT NULL
) STRICT;

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

-- Conversations with the tutor: their transcripts, and the tokens that reopen their agent
-- sessions.

CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (id),
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX conversations_by_learner ON conversations (learner_id, created_at);

CREATE TABLE transcript_items (
    conversation_id TEXT NOT NULL REFERENCES conversations (id),
    seq INTEGER NOT NULL, -- 1, 2, ... in the order they happened
    at TEXT NOT NULL,
    body TEXT NOT NULL, -- TranscriptItem JSON
    PRIMARY KEY (conversation_id, seq)
) STRICT;

-- A token only means something to the backend that issued it. The latest one per backend is
-- the one to resume with.
CREATE TABLE resume_tokens (
    conversation_id TEXT NOT NULL REFERENCES conversations (id),
    backend TEXT NOT NULL,
    token TEXT NOT NULL,
    at TEXT NOT NULL
) STRICT;

CREATE INDEX resume_tokens_by_conversation ON resume_tokens (conversation_id, backend);
