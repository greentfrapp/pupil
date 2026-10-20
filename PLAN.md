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
- **Answers go from the screen to the grader, never through the agent,** and answer keys never
  reach the client before the learner answers.

### New
- **No chat. The agent works behind the screens.** Each topic keeps one agent conversation as
  its hidden working log. Learner actions (finishing a lesson, giving feedback, asking about a
  question) are sent to it as structured messages, like `quiz_results` today. The agent replies
  with tool calls (`create_lesson`, `propose_revision`, …); its prose isn't shown, except
  where a screen asks for text, such as an answer to "Ask about this".
- **Teach through questions.** The default is to teach inside the question ("In Python, `//`
  divides and rounds down. What is `7 // 2`?"), with the explanation after a wrong answer as a
  tiny lesson. A one-screen **teach card** is allowed before a brand-new concept, sparingly.
- **Duolingo-style feedback:** each answer is checked as soon as it is given, and questions
  answered wrongly come back at the end of the lesson.
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
| Lots of quick questions can stay shallow | "Why?" questions, interleaving, spaced review (step 5) |
| Generating a lesson takes seconds to tens of seconds | Generate the next lesson in the background (step 3) |
| Physical skills | Quizzes cover the theory only; accepted |

## Roadmap

Each step is its own branch, can be merged on its own and builds on the ones before.

| Step | Branch | Contents | Depends on | Status |
|---|---|---|---|---|
| 1 | `lessons` | Lessons made of questions and teach cards; checking each answer as it's given; wrongly answered questions repeated; a lesson player replacing the quiz modal | — | Not started |
| 2 | `question-types` | Fill in the blank, ordering and matching, with grading and inputs in the player | 1 | Not started |
| 3 | `topic-path` | Topic intake (one line plus tap-to-answer setup questions), placement, a path screen showing the syllabus, and the next lesson generated in the background. Removes the chat. | 1 | Not started |
| 4 | `steering` | One-tap lesson feedback, syllabus proposals to accept or skip, and "Ask about this" | 3 | Not started |
| 5 | `review` | Mastery computed from evidence, path progress, and spaced review lessons | 3 | Not started |

### Step 1: lessons
- **Model: the quiz type is extended and renamed to `Lesson`.** A lesson is an ordered list of
  items, each a question (the existing union) or a teach card (title, short text). Placement
  and checkpoint quizzes become lessons without teach cards, so grading, attempts, evidence and
  the learner view carry over. The rename covers the `quizzes` table, the API and the tools.
  Stored quizzes keep `questions` rather than `items`, so a migration rewrites them or the
  model still accepts the old shape when loading.
- **Per-answer checking:** the answer key can't go to the client, so the player sends each
  answer to the server and gets back right/wrong plus the explanation. The attempt is final
  when the lesson ends.
- **Every try counts as evidence,** so improvement shows. Each piece of evidence records
  whether it was the first try or a repeat within the lesson: a repeat comes just after the
  explanation, so it shows recall more than learning. How much each kind counts towards
  mastery is decided in step 5.
- **Agent tool:** `create_lesson` replaces `create_quiz`, with guidance on teaching in the
  question and using teach cards sparingly.
- **Client:** a full-screen lesson player with a progress bar, a check button, and right/wrong
  feedback after each answer.

### Step 2: question types
- Fill in the blank (typed or picked from a word bank), ordering (put steps in order) and
  matching (pair items). Each needs a model, grading, a learner view and a player input.

### Step 3: topic path
- **Intake:** the learner types what they want to learn; the agent replies with two or three
  setup questions to tap (goal, current level, time per day), then a placement lesson, then
  the syllabus.
- **Path screen:** the syllabus as a path of units with the next lesson highlighted, and a list
  of topics to switch between.
- **Background generation:** after a lesson ends, the agent prepares the next one while the
  learner looks at their results.
- The chat UI and its endpoints for typed messages are removed or reduced to what intake needs.

### Step 4: steering
- **After each lesson:** "Too easy / About right / Too hard", plus optional chips ("More
  examples", "More real-world"), sent to the agent with the results.
- **Syllabus proposals:** a `propose_revision` tool whose change is shown as a card ("Add a unit
  on window functions?"); accepting applies it through the existing revision checks. The
  learner can also ask for more on a unit or to skip one.
- **"Ask about this":** a short answer card about the question or explanation on screen.

### Step 5: review
- Mastery per objective computed from evidence, shown on the path, deciding how much repeats
  within a lesson count compared with first tries.
- Review lessons that bring back weak or due objectives, scheduled by spaced repetition.

## Later, not yet scheduled
- **LLM-graded free-text answers** with a rubric, for open-ended skills.
- **Wrong answer keys:** "Report a problem", correcting a key after an attempt, and replacing a
  lesson; maybe a second model check when a lesson is created.
- **Engagement:** streaks, daily goals, XP.
- **Evolving stored JSON:** stored bodies must stay readable as the models change.
- **Learner data:** export, deletion and backups of `~/Pupil/pupil.db`.
- **Remote mode:** authentication, and mapping requests to a `learner_id`.
