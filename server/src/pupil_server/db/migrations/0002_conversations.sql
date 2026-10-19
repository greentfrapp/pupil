-- Conversations with the tutor: their transcripts, and the tokens that reopen their agent
-- sessions. Append-only, like the learning tables.

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
