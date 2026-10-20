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
| 1 | `base-types` | Syllabus, quiz/question and progress models, plus grading. Pure Python with tests: no database, tools or API. | — | Done (not merged) |
| 2 | `db` | SQLite foundation (`Database`, migrations, startup wiring), `learner_id`, and repositories for syllabi, quizzes, attempts and evidence | 1 | Done (not merged) |
| 3 | `learning-tools` | Agent tools on top of the repositories, wired into the demo tutor, plus a billed live test of the tool schemas | 2 | Done (not merged) |
| 4 | `conversations` | Saved transcripts, and reopening a conversation after a restart using its resume token | 2 (can run in parallel with 3) | Done (not merged) |
| 5 | `quiz-ui` | Quiz-taking interface: quizzes served without answers, the answer key kept out of the chat stream, answers submitted by the UI, and results sent back to the agent | 3, 4 | Done (not merged) |

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
  raises `TypeError`.
  - Multiple choice: the set of chosen ids must equal the set of correct ids.
  - Numeric: `abs(value - answer) <= tolerance`.
- **Quizzes:** `Quiz(id, title, purpose: Literal["placement", "checkpoint"], syllabus_id: str | None, questions (≥1))`,
  with unique question ids. A checkpoint quiz needs a `syllabus_id`, and a quiz without one
  can't have tagged questions. `Quiz.check_tags(syllabus)` makes sure every question has at least
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
  - A checkpoint quiz without a syllabus, and tags on a quiz without one, are rejected.
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
- **Access:** the standard library's `sqlite3` with repository classes. Rather than
  `asyncio.to_thread`, `Database` keeps its one connection on a single worker thread, so calls
  never overlap, even when the request awaiting one is cancelled. Each call is one transaction.
  Migrations are numbered SQL files (`db/migrations/NNNN_name.sql`) tracked by
  `PRAGMA user_version`, and a database newer than the code is refused.
- **Learners:** `learner_id` on every record, with the local learner (`lrn_local`) seeded at
  startup. Every repository method takes the learner and sees only their records.
- **Conventions:** ids are prefixed random strings (`lrn_`, `syl_`, `quiz_`, `att_`, `conv_`),
  made with `new_id`, and timestamps are ISO 8601 UTC text. Model timestamps must have a
  timezone.
- **As built (`db/learning.py`):**
  - `SyllabusRepo`: `create` stores revision 1. `revise` stores the next revision, and refuses
    a change based on a revision that is no longer the latest (`StaleRevision`). `get` returns
    the latest or a given revision, and `list_latest` lists the learner's syllabi.
  - `QuizRepo`: `create` checks a syllabus quiz's tags against the latest revision.
  - `AttemptRepo`: `submit` grades an attempt and stores it, with a `question_results` row
    per question and, for a syllabus quiz, an `evidence` row per tagged objective, in one
    transaction. `get` and `results` read them back.
  - `EvidenceRepo.for_syllabus` lists the evidence, oldest first. Mastery is still to come.
  - Missing records raise `NotFound` and reused ids raise `AlreadyExists`.

### Step 3: agent tools

- `create_syllabus`, `revise_syllabus` (whose description states the objective-id rule),
  `get_syllabus`, `create_quiz` and `submit_quiz_answers` (graded in code, never by the model).
- Validation errors go back to the agent as error tool results, so it can correct itself.
- **Risk:** the question union produces a JSON schema with `oneOf`, `$defs` and `$ref`. Claude
  must accept that as a tool input schema; the live test checks it. If it fails, inline the
  schema so it has no `$ref`s.
- **As built (`learning/tools.py`):**
  - `learning_tools(db, learner_id)` builds the tools for one learner. The tools assign ids
    and timestamps, so the agent never makes them up.
  - Added `list_syllabi`, so a new conversation can find the learner's existing syllabi.
  - `revise_syllabus` takes the whole syllabus plus `based_on_revision`; a stale revision comes
    back as an error telling the agent to read it again.
  - Model field docstrings appear as descriptions in the tool schemas, and unknown fields are
    refused rather than ignored.
  - **The objective-id rule is checked, not just described.** Code can't tell whether new
    wording is the same skill, so these checks guard the cases that lose or misattribute
    progress:
    - New objectives get their ids from the tools; the agent leaves the id out. Keeping an
      objective means copying its id, and an id not in the current revision is refused.
    - An objective the learner has evidence on can only be dropped by listing it in
      `retired_objectives`; otherwise the revision is refused. Objectives without evidence
      can be dropped freely.
    - `revise_syllabus` returns the objectives added, reworded and removed, and warns when an
      objective with evidence was reworded, asking the agent to confirm it is the same skill.
  - The demo tutor gets the tools for the local learner, and its prompt describes the loop:
    placement quiz, syllabus, checkpoints, revisions.
  - The live test (`pytest -m live`) asks Claude to create a quiz with every question type
    and submit answers to it. It passed, so Claude accepts the schemas as they are and no
    inlining is needed.

### Step 4: conversations

- Each conversation's resume token and its syllabus link are stored, along with **full
  transcripts**: the user's messages, plus the agent's events with each run of streamed text
  merged into one item.
- A conversation that exists in the database but not in memory (after a restart) is reopened
  with its stored resume token.
- **As built:**
  - Tables (`0002_conversations.sql`): `conversations`, `transcript_items` (one row per item,
    numbered in order) and `resume_tokens` (one row per new token; the latest per backend
    wins, since a token only means something to the backend that issued it).
  - `ConversationRepo` (`db/conversations.py`) and the `Conversations` service
    (`conversations/service.py`), which records each turn as it streams and reopens sessions.
    Text is saved when a run ends, and what was said is kept even if the client goes away
    mid-turn.
  - Agent sessions open with a conversation's first message, and reopen from the latest
    token whenever a message arrives with no live session. If the backend can't resume, a
    fresh session starts: the transcript is kept, but the agent has no memory of it.
  - The API moved from `/api/chat/sessions` to `/api/conversations`: `POST` to start,
    `GET` to list (newest first), `GET /{id}` for the transcript, `POST /{id}/messages` to
    stream a turn, and `DELETE /{id}/session` to release the live session while keeping the
    conversation.
  - The client remembers its conversation in `localStorage`, rebuilds the chat from the
    transcript on load, and has a New chat button.
  - **Deferred: the syllabus link.** Nothing reads it yet, and when to set it (at start,
    when the agent creates a syllabus, or by the learner) is best decided with the syllabus
    view.
  - **Known gaps:** transcripts include `create_quiz` inputs, so they carry answer keys, like
    the live stream (fixed in step 5). Reloading the page leaves the live session open until
    the next New chat or shutdown, which is harmless because the reload picks the same
    conversation back up.

### Step 5: quiz UI

Quizzes are taken in their own interface, not in the chat. The agent writes the whole quiz in
one `create_quiz` call, tells the learner it is ready and ends its turn. The UI then shows the
questions one at a time. (The tutor's prompt already asks for this.)

- **Quizzes without answers:** `GET /api/quizzes/{id}` returns the learner's view of a quiz,
  without `correct`, `answer`, `accepted` or `explanation` fields. Explanations come back with
  the results.
- **Keeping the answer key out of the chat stream:** today every `tool_call` event carries the
  tool's full input, so `create_quiz` would send the answers to the browser. Its input is
  stripped from the stream, and the client opens the quiz from the `quiz_id` in the tool result.
- **Answers come from the UI:** `POST /api/quizzes/{id}/attempts` grades and stores them with
  `AttemptRepo.submit`, and returns each question's result and explanation. The agent never
  relays answers, so it can't alter them. `submit_quiz_answers` stays for chat-only use, or is
  dropped.
- **Results go back to the agent:** when the learner finishes, the app sends the results into
  the conversation as the next message (e.g. "Quiz finished: 3 of 5 right; q2 and q4 wrong"), so
  the agent can explain mistakes and revise the syllabus. This needs messages the learner didn't
  type, which builds on step 4's transcripts.
- **Client:** a quiz component with one screen per question type, and TypeScript types for the
  learner's view of a quiz and for results.
- **As built:**
  - `learner_view` (`learning/quiz.py`) lists the fields a learner may see, rather than
    removing the answer fields, so an answer field added later stays hidden by default.
  - Tools can set `hide_input`; `create_quiz` does. The conversation service blanks those
    tools' inputs before streaming or saving them. Transcripts saved before this change may
    still hold answer keys.
  - **A quiz is answered once.** A second submission is refused (409), and `GET` returns the
    results instead, so a reload shows the results rather than a fresh quiz. Results include
    the learner's answer and the explanation, but not the correct answer, which the
    explanation can give.
  - **`submit_quiz_answers` is dropped,** so the agent can't record answers itself.
  - `POST /api/conversations/{id}/quiz-results` takes an attempt id; the app writes the
    message from the stored attempt (`describe_attempt`: the score, and what the learner
    answered for each wrong question). It is saved as a `quiz_results` transcript item.
  - Client: `QuizRunner.vue` opens from a Take the quiz button under the tutor's message.
    It shows one question at a time and, after submitting, the results. Meanwhile the chat
    reports them to the agent and streams its reply.
  - **Not done:** replacing a quiz (`create_quiz(replaces=...)`) and correcting a wrong
    answer key after an attempt, both discussed and deferred.

## Other gaps, not yet scheduled

- **Evolving stored JSON:** stored bodies must stay readable as the models change. Model changes
  must be backward-compatible, or a migration must rewrite the stored JSON.
- **Learner data:** export and deletion, since this is a consumer app holding learner
  transcripts. Also backups of `~/Pupil/pupil.db`.
- **Remote mode:** authentication, and mapping requests to a `learner_id`.
- **UI:** a transcript view, a syllabus view, and TypeScript types for these models. The
  quiz-taking UI is step 5.
