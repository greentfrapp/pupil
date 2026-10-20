# Plan: quiz-first learning, without a chat

Pupil should feel like Duolingo: short, playful lessons that teach mostly by asking, not by
lecturing. The learner never chats with the agent. The agent still plans and adapts everything,
but it reaches the learner through structured screens it fills in with tools: a path, lessons,
proposals and short answers.

## Built so far

- **Models** (`learning/`): syllabi with units, objectives and prerequisites; quizzes with
  multiple choice, true/false, numeric and text-match questions; grading; evidence types.
- **Storage** (`db/`): SQLite with migrations; append-only syllabi (one row per revision),
  quizzes, attempts, per-question results and per-objective evidence, all scoped by
  `learner_id`.
- **Agent tools** (`learning/tools.py`): `create_syllabus`, `revise_syllabus`, `get_syllabus`,
  `list_syllabi` and `create_quiz`. Objective ids are assigned and checked by the server.
- **Conversations** (`conversations/`): saved transcripts, resume tokens and reopening a
  session after a restart. Tool inputs can be hidden (`hide_input`), which keeps answer keys
  off the client.
- **Quiz screen:** quizzes served without answers, one attempt per quiz (enforced in the
  submit transaction), and results reported to the agent as a `quiz_results` message.
- **Client:** a chat box with a quiz modal. The chat goes away in this plan.

## Design

### Still holds
- **Progress is kept separate from the syllabus.** Mastery and "what's next" are computed from
  evidence, never stored on the syllabus, so revising the plan doesn't lose what the learner
  has shown they know.
- **Objective ids are stable:** a reworded skill keeps its id; a different skill gets a new one.
- **Answers never go through the agent.** The lesson player grades them, by code, and the
  server stores the results as given, without grading again. It checks that an attempt fits
  the lesson and keeps the learner's responses, so results could be regraded if grading had a
  bug. The answer key is sent to the client with the lesson.

### New
- **No chat, and no long-running conversation.** Each job the agent does is a fresh, one-off
  run: intake, planning the syllabus, the next lesson, answering "Ask about this". A run gets
  instructions for its job, a short brief built from the database, and the tools it needs.
  Nothing is resumed, so cost per lesson stays flat, restarts don't matter, and runs don't
  queue behind each other. Runs are logged for debugging but never replayed to the agent.
- **What the agent knows comes from the database:** the syllabus, evidence (and mastery, from
  step 6), past lessons and their results, a **profile** per topic (setup answers, and
  preferences from feedback) and **notes** the agent writes with a tool ("prefers
  real-world examples"). Anything from free text must be written down this way, or it's
  forgotten.
- **Teach through questions.** The default is to teach inside the question ("In Python, `//`
  divides and rounds down. What is `7 // 2`?"). A one-screen **teach card** is allowed before
  a brand-new concept, sparingly.
- **Duolingo-style lessons:** a lesson takes 1–3 minutes. After each question the learner sees
  whether they were right, the correct answer and a short explanation; a question is never
  retried on its own. Once a lesson is finished it can be retried as a whole, rerunning the
  same questions shuffled where order doesn't matter, so nothing is generated again. Quitting
  part-way means starting again; there is nothing to resume. We don't try hard to stop
  learners gaming lessons; it only hurts their own learning.
- **Results are pulled by the agent, not pushed to it.** Finishing a lesson doesn't start an
  agent run. Results are read when the agent next has a job, such as preparing a lesson or
  revising the syllabus, so it sees everything since its last run at once.
- **Learners steer by tapping, not typing:** setup questions, one-tap lesson feedback, and
  syllabus changes proposed as cards to accept or skip. The one free-text box is "Ask about
  this", tied to the question or explanation on screen.

### Known limits
| Limit | Plan |
|---|---|
| Brand-new concepts can't be guessed into | Teach cards, kept short and rare |
| Open-ended skills (writing, argument, design) can't be graded by our question types | LLM-graded free text with a rubric (later): costs money, adds latency, can be inconsistent |
| Multiple choice tests recognition, not production | Fill in the blank, ordering and matching (step 2); maybe running code later |
| Generated answer keys can be wrong | "Report a problem" and answer-key correction (later); maybe a second model check at creation |
| Lots of quick questions can stay shallow | "Why?" questions, interleaving, spaced review (step 6) |
| Generating a lesson takes seconds to tens of seconds | Generate the next lesson in the background (step 3) |
| The agent only knows what the brief and notes tell it | Keep the brief complete but bounded; review what it holds as steps land |
| Physical skills | Quizzes cover the theory only; accepted |

## Roadmap

Each step is its own branch, can be merged on its own and builds on the ones before.

| Step | Branch | Contents | Depends on | Status |
|---|---|---|---|---|
| 1 | `lessons` | Lessons made of questions and teach cards; each answer checked as it's given, with the correct answer and explanation shown; whole-lesson retries, shuffled; results read by the agent instead of reported; a lesson player replacing the quiz modal | — | Done (not merged) |
| 2 | `question-types` | Fill in the blank, ordering and matching, with grading and inputs in the player | 1 | Done (not merged) |
| 3 | `agent-runs` | Topics; one-off agent runs with a brief, profile and notes; run logs; the next lesson generated in the background, one run per topic at a time. Mostly server work. | 1 | Not started |
| 4 | `topic-path` | Fixed setup questions, placement with "I don't know", a path screen; removes the chat and resuming conversations. Mostly client work. | 3 | Not started |
| 5 | `steering` | One-tap lesson feedback, syllabus proposals to accept or skip, and "Ask about this" | 4 | Not started |
| 6 | `review` | Mastery computed from evidence, path progress, and spaced review lessons | 4 | Not started |

### Step 1: lessons
- **Model: the quiz type is extended and renamed to `Lesson`.** A lesson is an ordered list of
  items, each a question (the existing union) or a teach card (title, short text). Attempts
  and evidence carry over. The rename covers the `quizzes` table, the API and the tools.
- **Purposes are `placement` and `lesson`** (`review` comes in step 6); checkpoint quizzes are
  dropped until a "test out of this unit" is wanted. A placement lesson has no teach cards
  (checked by the model) and can't be retried; redoing placement means starting the topic
  again.
- **Taking a lesson:** the lesson comes with its answer key, and the player grades each answer
  as it's given, showing whether it was right, the correct answer and the explanation. When
  the lesson ends, the player submits every answer with its grade as one attempt; the server
  checks it fits the lesson and stores it without grading again. A quit lesson stores nothing.
- **Correct answers for the learner:** the player describes each question type's answer for
  display: the correct option(s), the number with its unit, or the first accepted text.
- **Explanations are required and short** (a sentence or two), and shown after every answer,
  right or wrong, so a lucky guess still teaches.
- **Retries:** the one-attempt rule is dropped. A finished lesson can be retried as a new
  attempt. Option ids don't change, so shuffling doesn't affect grading.
- **Shuffling respects order where it matters.** Teach cards stay in place and questions are
  shuffled only between them, so a card still comes before the questions that use it. A
  lesson whose questions build on each other is marked to keep its order. A multiple-choice
  question whose options depend on position ("All of the above") is marked to keep its
  option order.
- **Every attempt counts as evidence,** so improvement shows. Attempts are numbered per lesson,
  so first attempts can be told from retries, which test recall of answers already shown. How
  much each counts towards mastery is decided in step 6.
- **Schema:** the `quizzes` table becomes `lessons`, stored bodies hold `items` rather than
  `questions`, and attempts are numbered per lesson. Attempts are still written once, when
  submitted, so the tables stay append-only. **Existing data is reset, not migrated:** the
  migrations are squashed into a new `0001`, and an old database is refused as too new
  (`DatabaseTooNew`) until `~/Pupil/pupil.db` is deleted.
- **Results aren't reported to the agent.** The `quiz_results` message and its endpoint are
  removed. While the chat remains, the agent reads results with a tool (e.g. `recent_results`)
  when the learner asks for the next lesson; from step 3 they go in the run's brief.
- **Agent tool:** `create_lesson` replaces `create_quiz`, with guidance on teaching in the
  question, using teach cards sparingly, keeping explanations short, and marking lessons and
  questions whose order matters.
- **Client:** a full-screen lesson player with a progress bar, a check button, and after each
  answer whether it was right, the correct answer and the explanation; then a results screen
  with a Retry button.
- **As built:**
  - `learning/lesson.py` replaces `quiz.py`: `Lesson` (`items`, `keep_order`), `TeachCard`,
    `MultipleChoice.keep_option_order`, a required `explanation`, `Attempt` (an `Answer` of
    response and grade per question) and `GradedAttempt` (attempt, number, results). The
    server no longer grades: `check_attempt` makes sure an attempt answers every question
    with the right kind of response, and takes objective ids from the lesson.
  - `shuffled(lesson, rng)` shuffles questions between teach cards, and options unless kept in
    order.
  - `LessonRepo`; `AttemptRepo.submit` numbers attempts in the same transaction as the insert
    and raises `PlacementTaken` for a second placement attempt; `get`, `for_lesson` and
    `recent` return graded attempts. Evidence has `attempt_number`.
  - API: `GET /api/lessons/{id}` (the shuffled lesson with its answers, and attempt summaries)
    and `POST /api/lessons/{id}/attempts` (201; 409 for a retaken placement; 422 for an
    attempt that doesn't fit).
  - Tools: `create_lesson` and `recent_results` (newest first, each described with its
    attempt number). The conversation `quiz-results` endpoint, the `quiz_results` transcript
    item and `hide_input` are gone.
  - Client: `grading.ts` (`grade`, `answerText`) with Vitest tests (`pnpm test`);
    `LessonPlayer.vue` replaces `QuizRunner.vue`; the chat shows a Start the lesson button
    under `create_lesson`.
  - The billed live test passes: Claude fills in `create_lesson`'s schema, teach card
    included. Not verified: the player in a browser.

### Step 2: question types
- Fill in the blank (typed or picked from a word bank), ordering (put steps in order) and
  matching (pair items). Each needs a model and a response check on the server, and grading,
  a description of its correct answer and an input in the player.
- **As built:**
  - `FillBlank`: `text` with `___` (three or more underscores) per blank, `blanks` (each with
    its accepted answers), an optional `word_bank` (each word used once; must hold every
    blank's first answer) and `case_sensitive`. Answered with `BlanksResponse(values)`.
  - `Ordering`: `sequence`, the items in the correct order. Answered with
    `OrderResponse(item_ids)`, which must place every item once.
  - `Matching`: `pairs` of `left` and `right`, each side unique. Answered with
    `MatchResponse(matches)`, pair id to pair id, which must match every item once.
  - All three are graded right or wrong as a whole; there's no partial credit.
  - `create_lesson` now asks for a mix of types, favouring fill in the blank, text match,
    ordering and matching over true/false and multiple choice.
  - Ordering and matching are shuffled for display by the client (`shuffle.ts`), because an
    ordering's stored order is its answer; an ordering never starts out solved. The server
    still shuffles questions and multiple-choice options.
  - Client: each question type has its own input component in `components/inputs/`, which
    reports a whole response or none; `grading.ts` gains the new types and `responseText`.
  - Not verified: the new inputs in a browser, and the billed live schema test (now asking
    for every question type).

### Step 3: agent runs
- **Topics:** a `topics` table (id, learner, the line they typed, created). Everything else
  points at the topic, so the topic row never changes and the tables stay append-only: setup
  answers, syllabi and lessons get a `topic_id` (the newest syllabus for a topic is its plan;
  a placement lesson belongs to the topic before any syllabus exists), and so do feedback,
  notes and runs. A topic's next lesson is ready when it has a lesson with no attempts.
- **Profile and notes are per topic** for now; sharing them across topics can come later.
- **One-off agent runs:** a brief built from the database for each job, the topic's profile,
  and a tool for the agent to write notes.
- **The brief holds what every run needs:** the profile, notes, the current syllabus, results
  since the last run, and a one-line summary of each recent lesson. Details needed only
  sometimes (a past lesson's questions, older evidence) are fetched with read tools.
- **Run logs:** `conversations` becomes `runs`, each recording its job (intake, next lesson,
  ask), topic, start and finish times and cost; `transcript_items` stays under runs. Kept for
  debugging bad lessons and tracking cost, never replayed to the agent.
- **Background generation:** when a topic has no unstarted lesson ready, a run prepares the
  next one while the learner looks at their results. Its brief holds the results since the
  last run, and the same run can revise the syllabus. The client learns when it's ready.
  **At most one generation run per topic at a time:** a request that would start another
  while one is going waits for it instead. One server process, so an in-memory marker per
  topic is enough.
- Testable end to end with the fake backend before any new screens exist.

### Step 4: topic path
- **Intake:** the learner types what they want to learn, then answers fixed setup questions
  written into the app, not by the agent (instant and free), one per screen. The answers go
  in the brief as structured fields, and the agent's instructions say what each answer
  changes:
  1. **"Why are you learning this?"** Shapes the syllabus's units, their order, and the kind
     of question.
     | Answer | Syllabus | Lessons |
     |---|---|---|
     | For work | Practical tasks first; theory only as needed | Realistic scenarios, "what would you do" questions |
     | For a course or exam | The standard curriculum, in its usual order | Exam-style questions and wording |
     | To build something | Ordered by what the project needs next | Questions framed around the project |
     | Curiosity | Big ideas and intuition first; broad rather than deep | "Why" questions, surprising facts |
  2. **"How far do you want to go?"** Sets the syllabus's size and depth: a quick overview (a
     few units on the key ideas, easier questions), solid working knowledge (a full syllabus
     to confident everyday use), or deep expertise (advanced units and edge cases, harder
     questions).
  3. **"How much do you know already?"** Decides placement: new to this (no placement; start
     at the beginning), the basics (placement from basics to intermediate), or knows it well
     (placement from intermediate up).
  4. **"Anything specific?"** Optional free text, e.g. "AP Calculus BC" or "a Discord bot".
- **After placement, the plan is shown back** with a line saying why it looks that way
  ("Exam-focused, 6 units, starting from functions since you know the basics").
- **Placement:** a placement lesson, with an **"I don't know"** button counted as wrong so
  learners don't guess their way too far ahead. Feedback after each answer is as in any
  lesson. Placement has no syllabus, so it gives no evidence; its results go in the brief for
  the run that writes the syllabus.
- **Path screen:** the syllabus as a path of units with the next lesson highlighted, and a list
  of topics to switch between.
- **Removed:** the chat UI, typed-message endpoints, and resuming conversations (resume tokens,
  the session store, reopening sessions after a restart).

### Step 5: steering
- **After each lesson:** "Too easy / About right / Too hard", plus optional chips ("More
  examples", "More real-world"), saved to the learner profile and in the next brief.
- **Syllabus proposals:** a `propose_revision` tool whose change is shown as a card ("Add a unit
  on window functions?"); accepting applies it through the existing revision checks. The
  learner can also ask for more on a unit or to skip one.
- **"Ask about this":** a one-off run answering a question about what's on screen, shown as a
  short answer card. No follow-up questions, as in Duolingo. If the question reveals something
  lasting ("keeps confusing joins and unions"), the run writes a note.

### Step 6: review
- Mastery per objective computed from evidence, shown on the path, deciding how much retries
  count compared with first attempts.
- Review lessons that bring back weak or due objectives, scheduled by spaced repetition.

## Later, not yet scheduled
- **LLM-graded free-text answers** with a rubric, for open-ended skills. These are graded on
  the server, unlike the other question types.
- **Wrong answer keys:** "Report a problem", correcting a key after an attempt, and replacing a
  lesson; maybe a second model check when a lesson is created.
- **Engagement:** streaks, daily goals, XP.
- **Evolving stored JSON:** stored bodies must stay readable as the models change.
- **Learner data:** export, deletion and backups of `~/Pupil/pupil.db`.
- **Remote mode:** authentication, and mapping requests to a `learner_id`.
