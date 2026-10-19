# Plan: learning models, database, agent tools and conversations

Pupil adapts teaching to the learner's zone of proximal development. This plan covers the core
domain types and the work that builds on them:

- **Quizzes** assess the learner: placement at the start (which shapes the syllabus) and
  checkpoints later (what they've learned).
- **Syllabi** are the learning roadmap for one topic. The learner and the agent plan with it and
  keep revising it.

The work is split into four branches. Each can be merged on its own and builds on the one before.

## Roadmap

| Step | Branch | Contents | Depends on | Status |
|---|---|---|---|---|
| 1 | `base-types` | Syllabus, quiz/question and progress models, plus grading. Pure Python with tests: no database, tools or API. | — | Planned |
| 2 | `db` | SQLite foundation (`Database`, migrations, startup wiring), `learner_id`, and repositories for syllabi, quizzes, attempts and evidence | 1 | Planned |
| 3 | `learning-tools` | Agent tools on top of the repositories, wired into the demo tutor, plus a billed live test of the tool schemas | 2 | Planned |
| 4 | `conversations` | Saved transcripts, and reopening a conversation after a restart using its resume token | 2 (can run in parallel with 3) | Planned |

## Design: progress is kept separate from the syllabus

- The syllabus is only the plan. Units contain **objectives with stable ids** and list
  prerequisite units.
- Questions list the objective ids they test. Grading an attempt produces per-objective
  **evidence**.
- Mastery, unit status and "what's next" (unmastered units whose prerequisites are mastered,
  i.e. the zone of proximal development) are computed from the evidence; they are never stored
  on the syllabus. Step 1 adds only the progress **types**; the computing comes later.
- **Why:** the agent can revise units without losing what the learner has shown they know, and
  mastery can be traced back to specific answers.
- **The rule the agent must follow:** a reworded skill keeps its objective id; a different skill
  gets a new id. This rule goes in the tool descriptions in step 3.
- **Placement quizzes may have no syllabus.** Their questions then have no tags, and their
  results inform the syllabus design directly.

## Step 1: models (`server/src/pupil_server/learning/`)

### `syllabus.py`

- `Objective(id, text)`
- `Unit(id, title, summary, objectives: list[Objective] (≥1), prerequisites: list[str] = [], estimated_minutes: int | None)`
- `Syllabus(id, topic, goal, units (≥1), revision: int = 1)`. A model validator checks that unit
  ids and objective ids are unique, that prerequisites name existing units, and that there are
  **no cycles**. Its error names the offending ids, so the agent can fix them.
- `Syllabus.units_in_order()` returns units in prerequisite order (stable, keeping the authored
  order where possible). `objective_ids()` returns all objective ids.

### `quiz.py`

- **Questions** are a union told apart by `kind`, all sharing
  `id, prompt, objective_ids: list[str] = [], difficulty: int (1–5), explanation: str | None`:
  - `MultipleChoice(kind="multiple_choice", options: list[Option(id, text)] (≥2), correct: list[str] (≥1), multiple: bool = False)`.
    Validation: option ids are unique, every correct id is a real option, and a single-answer
    question has exactly one correct option.
  - `TrueFalse(kind="true_false", answer: bool)`
  - `Numeric(kind="numeric", answer: float, tolerance: float = 0 (≥0), unit: str | None)`
  - `TextMatch(kind="text_match", accepted: list[str] (≥1), case_sensitive: bool = False)`.
    Before comparing, answers are trimmed and runs of whitespace are collapsed (and case is
    ignored unless `case_sensitive`).
- **Responses** mirror the question types: `ChoiceResponse(option_ids)`, `BoolResponse(value)`,
  `NumberResponse(value)` and `TextResponse(text)`, also told apart by `kind`.
- **Grading:** each question has `grade(response) -> bool`, and a response of the wrong kind
  raises `ValueError`.
  - Multiple choice: the set of chosen ids must equal the set of correct ids.
  - Numeric: `abs(value - answer) <= tolerance`.
- **Quizzes:** `Quiz(id, title, purpose: Literal["placement", "checkpoint"], syllabus_id: str | None, questions (≥1))`,
  with unique question ids. `Quiz.check_tags(syllabus)` makes sure every question has at least
  one tag and every tag exists in the syllabus. Step 2 calls it when storing a syllabus-linked
  quiz.
- **Attempts:** `QuizAttempt(id, quiz_id, responses: dict[str, Response], submitted_at)` and
  `QuestionResult(question_id, correct, objective_ids)`. `grade_attempt(quiz, attempt) -> list[QuestionResult]`
  rejects unknown question ids and counts unanswered questions as incorrect.

### `progress.py` (types only)

- `Evidence(objective_id, attempt_id, question_id, correct, at)`
- `Mastery = Literal["unknown", "learning", "mastered"]`
- `ObjectiveProgress(objective_id, mastery: Mastery = "unknown", evidence: list[Evidence] = [])`
- `LearnerProgress(learner_id, syllabus_id, objectives: dict[str, ObjectiveProgress])`

### Tests (`server/tests/`)

- **`test_learning_syllabus.py`:**
  - A valid syllabus is accepted.
  - These are rejected, each with a message naming the offending ids: duplicate unit ids,
    duplicate objective ids, an unknown prerequisite, a cycle (including a unit that requires
    itself).
  - `units_in_order` respects prerequisites and otherwise keeps the authored order.
- **`test_learning_quiz.py`:**
  - Multiple-choice validation: a single-answer question with two correct options, an unknown
    correct id, duplicate option ids.
  - Grading, right and wrong, for each type: multiple choice with single and multiple answers
    (a subset of the right answers is wrong), true/false, numeric exactly at its tolerance and
    just past it, text normalisation and case sensitivity.
  - A response of the wrong kind raises an error.
  - `grade_attempt` handles unanswered questions and rejects unknown ids.
  - `check_tags` catches unknown tags and untagged questions.
  - A response told apart by `kind` survives conversion to JSON and back. These are shaped by
    our own validators, and the database stores them as JSON in step 2.

### Commits

1. Syllabus models and tests
2. Quiz, question and progress models, grading and tests

## Decisions for later steps

### Step 2: database

- **Storage:** append-only tables. A syllabus revision is a new row, and quizzes, attempts and
  evidence are never updated. Whole documents (a syllabus revision, a quiz) are stored as
  pydantic JSON in `body` columns; anything queried per item (evidence, results) gets its own
  table.
- **Access:** the standard library's `sqlite3` with repository classes, run off the event loop
  via `asyncio.to_thread`. Migrations are numbered SQL files tracked by `PRAGMA user_version`.
- **Learners:** `learner_id` on every record, with a seeded local learner (`lrn_local`).
- **Conventions:** ids are prefixed random strings (`lrn_`, `syl_`, `quiz_`, `att_`, `conv_`),
  and timestamps are ISO 8601 UTC text.

### Step 3: agent tools

- `create_syllabus`, `revise_syllabus` (whose description states the objective-id rule),
  `get_syllabus`, `create_quiz` and `submit_quiz_answers` (graded in code, never by the model).
- Validation errors go back to the agent as error tool results, so it can correct itself.
- **Risk:** the question union produces a JSON schema with `oneOf`, `$defs` and `$ref`. Claude
  must accept that as a tool input schema; the live test checks it. If it fails, inline the
  schema so it has no `$ref`s.

### Step 4: conversations

- Each conversation's resume token and its syllabus link are stored, along with **full
  transcripts**: the user's messages, plus the agent's events with each run of streamed text
  merged into one item.
- A conversation that exists in the database but not in memory (after a restart) is reopened
  with its stored resume token.

## Other gaps, not yet scheduled

- **Hiding the answer key:** a view of a quiz without its answers, needed before a quiz-taking
  UI sends quizzes to the browser.
- **Evolving stored JSON:** stored bodies must stay readable as the models change. Model changes
  must be backward-compatible, or a migration must rewrite the stored JSON.
- **Learner data:** export and deletion, since this is a consumer app holding learner
  transcripts. Also backups of `~/Pupil/pupil.db`.
- **Remote mode:** authentication, and mapping requests to a `learner_id`.
- **UI:** a transcript view, a quiz-taking UI, a syllabus view, and TypeScript types for these
  models.
