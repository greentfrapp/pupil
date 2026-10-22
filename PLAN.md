# Plan: quiz-first learning, without a chat

Pupil should feel like Duolingo: short, playful lessons that teach mostly by asking, not by
lecturing. The learner never chats with the agent. The agent still plans and adapts everything,
but it reaches the learner through structured screens it fills in with tools: a path, lessons,
proposals and short answers.

## Built so far

- **Models** (`learning/`): syllabi with units, objectives and prerequisites; lessons of
  questions (seven types) and teach cards; attempts; topics with their setup answers.
- **Storage** (`db/`): SQLite with migrations, append-only and scoped by `learner_id`:
  topics, notes, syllabi (a row per revision), lessons, attempts, per-question results,
  per-objective evidence, and the agent's runs with their logs.
- **Agent runs** (`runs/`): one-off runs per topic (placement, plan, next lesson) with a
  brief built from the database and the learning tools, at most one per topic at a time.
- **Client:** a home screen of topics, the setup questions, a topic screen with the plan and
  the path, and a lesson player that grades answers itself.

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
| 1 | `lessons` | Lessons made of questions and teach cards; each answer checked as it's given, with the correct answer and explanation shown; whole-lesson retries, shuffled; results read by the agent instead of reported; a lesson player replacing the quiz modal | — | Done |
| 2 | `question-types` | Fill in the blank, ordering and matching, with grading and inputs in the player | 1 | Done |
| 3 | `agent-runs` | Topics; one-off agent runs with a brief, profile and notes; run logs; the next lesson generated in the background, one run per topic at a time. Mostly server work. | 1 | Done |
| 4 | `topic-path` | Fixed setup questions, placement with "I don't know", a path screen; removes the chat and resuming conversations. Mostly client work. | 3 | Done |
| 4b | `lesson-stops` | Lessons as stops on the path, set by the plan; one lesson written ahead; topics that end, with Go further. From the first real session. | 4 | Done (not merged) |
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
  - The billed live test passes: Claude fills in `create_lesson` with a teach card and every
    question type. Not verified: the new inputs in a browser.

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
- **As built:**
  - **Jobs:** `placement`, then `plan` (a syllabus and the first lesson; straight away for a
    learner new to the topic), then `next_lesson` each time no lesson is waiting
    (`runs/jobs.py`). Creating a topic or submitting an attempt at one of its lessons calls
    `Runs.prepare`, which starts the job the topic needs unless a run is going or a lesson is
    waiting. `POST /api/topics/{id}/prepare` does the same, e.g. to try again after a failure.
  - **A run** (`runs/service.py`) is a fresh agent session: a system prompt saying how the
    setup answers shape the work, then the brief as its one message. Its tools are the
    learning tools for the topic: what they create is filed under it, `recent_results` is the
    topic's, and `add_note` and `get_lesson` are added. Afterwards the run is checked for what
    it should have made, and fails if it didn't (e.g. "the run didn't leave a lesson to take").
    A run cut off by shutdown records that it was.
  - **The brief** (`runs/brief.py`): the job, the request and setup answers, the notes, the
    syllabus as JSON, results of attempts since the last successful run started (at most 20),
    and a line on each of the 10 newest lessons.
  - **Storage** (migration `0002`): `topics` (the setup answers are a `Profile` stored with the
    topic, written once), `topic_id` on syllabi and lessons, `notes`, and `runs` with separate
    `run_ends` and `run_items`, so nothing is updated. The conversations tables are left for
    the chat until step 4 removes it, rather than renamed now.
  - **API:** `POST/GET /api/topics`, `GET /api/topics/{id}` (syllabus, lessons with attempt
    counts, `next_lesson_id`, and the last run's state: running, done or failed with why) and
    `POST /api/topics/{id}/prepare`. A running job is reported from memory, so it shows the
    moment the run starts.
  - The fake backend's scripted calls can take a function of earlier outputs, for ids the app
    assigns. A billed live test of a real placement run passes: Claude, given only the
    brief, wrote a placement lesson that the run's checks accepted.
  - **Left for step 4:** the screens, "I don't know", and the rationale shown with the plan.

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
- **As built:**
  - **Removed:** the chat (`ChatBox.vue`, `api/chat.ts`, the conversations endpoints and
    package, the demo tutor), `SessionStore`, and resume tokens in the agent backends.
    Migration `0003` drops the conversations tables. Run logs keep their items in
    `runs/log.py`. The learning tools always act for a topic, so `list_syllabi` is gone.
  - **The rationale:** `create_syllabus` and `revise_syllabus` take a required `rationale`,
    one line for the learner, stored on the syllabus. The plan job asks for it.
  - **"I don't know":** placement shows it next to Check; it's stored as an answer with no
    response, counted wrong, and described to the agent as "said they didn't know".
    Ordinary lessons don't offer it.
  - **API:** a topic has a `path`: the syllabus's units in learning order, each with its
    lessons. A lesson goes under the earliest unit it tests, so it appears once; placement
    and lessons testing only retired objectives aren't on the path.
  - **Client:** a home screen listing topics; the intake (the request, then the three
    questions as tappable cards, then "Anything specific?"); and a topic screen in three
    stages (`topicState.ts`, with tests). Before the plan, it shows the placement intro or
    the score, or "Building your plan…". With a plan and no lesson taken yet, it shows the
    goal, the rationale and the units, with "Start your first lesson". After that, it shows
    the path: units with their lessons, the next one highlighted. Units with no lessons yet
    are drawn faded and dashed, the cue for what isn't written yet. A footer says what's
    next: start it, "Writing your next lesson…" while a run goes (polled every 2 seconds),
    or the error with Try again. A finished lesson returns to the topic.
  - No URLs or browser history: the app switches between screens itself.
  - The billed live tests pass after the chat's removal: Claude fills in the learning
    tools' schemas for a topic, and a real placement run works. Not verified: the screens
    in a browser, and a plan run (with its rationale) with real Claude.

### Step 4b: lesson stops
From the first real session (Discworld: placement, plan, three lessons, about $0.20 and a
minute per run). Every run did its job, but a topic had no end: once every unit had a
lesson, nothing said what came next. And runs used notes as a work log, repeating the
brief, once even before they knew the lesson's id.
- **Lesson stops, as in Duolingo:** the plan says how many lessons each unit takes, so the
  whole path is known from the start. The topic is finished when every lesson on it is
  taken. Duolingo's courses are written in advance; here the stops are fixed in advance and
  their lessons written as the learner goes.
- **One lesson ahead:** runs keep two untaken lessons, the next and one more, so the learner
  doesn't wait (a run takes about a minute; a lesson two or three). Each lesson is written
  knowing all results but those of the lesson being taken. Weighed against writing a unit
  or the whole course at once (adapts less, wastes more when learners stop) and parallel
  runs (lessons that can't see each other overlap).
- **Go further:** a finished topic offers a run that adds units to the path; their lessons
  follow as before.
- **Notes are off** until step 5 gives learners a way to give feedback: `add_note` and the
  notes in the brief are commented out, and the table stays.
- **As built:**
  - `Unit.lessons` (1 to 10; required in `create_syllabus` and `revise_syllabus`) and
    `Lesson.unit_id` (required for a lesson, checked against the syllabus). `create_lesson`
    refuses a unit whose stops all have lessons.
  - `learning/path.py`: the path (units in learning order, each with its lessons) and the
    next stop without a lesson. A unit revised below the lessons it has keeps them.
  - `runs/state.py`: a topic's state (syllabus, lessons, untaken, path, next stop,
    finished, next job). `next_job` keeps `AHEAD = 2` untaken lessons until the stops run
    out. A run that did its job starts the next run the topic needs; a failed one doesn't.
    A run fails if it wrote no lesson (or, extending, added no stops).
  - The next-lesson brief names the stop ("lesson 2 of 3 (the unit's last) in unit
    'joins'"), and a unit's last lesson rounds it off. Recent lessons show their unit.
  - API: path units have `stops`; a topic has `finished`; `POST /api/topics/{id}/extend`
    (202; 409 when not finished or a run is going) starts the `extend` job.
  - Client: each unit shows its lessons then its unwritten stops, faded; the plan shows
    each unit's lesson count; the home screen "x of y lessons done"; a finished topic
    shows its score and Go further above the path.
  - Lessons from before this change have no unit, so they're on no unit of the path; a
    database from step 4 should be reset (the migrations are squashed before release).
  - Billed live tests pass for the new runs: a plan run with a rationale, whose follow-up
    run writes the second lesson for the next stop; and Go further on a finished topic,
    which adds units after the existing ones and then writes their first lesson. Not
    verified: in a browser.

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
