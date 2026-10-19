-- Learners, and the learning records: syllabi, quizzes, attempts and what they show.
-- Every table is append-only. Timestamps are ISO 8601 UTC text.

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

CREATE TABLE quizzes (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (id),
    syllabus_id TEXT, -- NULL for a placement quiz written before any syllabus
    body TEXT NOT NULL, -- Quiz JSON
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE attempts (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (id),
    quiz_id TEXT NOT NULL REFERENCES quizzes (id),
    body TEXT NOT NULL, -- QuizAttempt JSON, holding the learner's responses
    submitted_at TEXT NOT NULL
) STRICT;

-- How each question of an attempt was graded, including untagged placement questions.
CREATE TABLE question_results (
    attempt_id TEXT NOT NULL REFERENCES attempts (id),
    question_id TEXT NOT NULL,
    correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
    PRIMARY KEY (attempt_id, question_id)
) STRICT;

-- One row per objective a graded question tests, for quizzes tied to a syllabus.
CREATE TABLE evidence (
    learner_id TEXT NOT NULL REFERENCES learners (id),
    syllabus_id TEXT NOT NULL,
    objective_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
    at TEXT NOT NULL,
    PRIMARY KEY (attempt_id, question_id, objective_id),
    FOREIGN KEY (attempt_id, question_id) REFERENCES question_results (attempt_id, question_id)
) STRICT;

CREATE INDEX evidence_by_syllabus ON evidence (learner_id, syllabus_id, at);
