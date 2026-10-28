# Plan

## Next: lesson quality

Reviewing three runs on the same topic (Opus, Codex, Sonnet) found wrong answer keys and
giveaways on Sonnet, abstract lessons on Codex, few teach cards anywhere, and typed answers
marked wrong for small differences. Three branches, in order:

**`lesson-quality`**
- [x] Claude defaults to Opus.
- [x] Runs search the web to check facts they aren't sure of, and to scope a topic before planning.
- [x] Prompt guidance on writing questions, on placement finding the edge of what the learner knows, and on teach cards that motivate their idea.
- [x] `create_lesson` refuses word banks without wrong words, and typed answers given away in the question.

**`lenient-grading`**
- [ ] Typed answers forgive case, spacing, punctuation, hyphens, accents, a leading "the", British/American spelling, and one typo in answers of 6+ characters with no digits.
- [ ] An `exact` flag on a question turns typo and spelling forgiveness off.
- [ ] The prompt tells the agent about both.

**`markdown-rendering`**
- [ ] The lesson player renders Markdown in question prompts, explanations and teach cards, safely (no raw HTML from the agent). Codex already writes source links, such as `[Book overview](https://…)`, which show as raw text until then.
- [ ] The prompt tells the agent what Markdown it can use, and where.

## Known issues

- **Lessons written ahead can repeat questions:** the brief lists an untaken lesson by title only, so the next one can ask the same thing (John Keel in the Discworld session). Runs are now told to read recent lessons first; the firmer fix is to give the brief their questions.
- **A run cut off by a restart** isn't run again until the learner finishes a lesson or taps Try again, losing the lesson written ahead once. Prepare every topic at startup.
- **Explanations may run long,** up to about 210 characters.

## Possible extensions

### Steering
- **After each lesson:** "Too easy / About right / Too hard", plus optional chips ("More examples", "More real-world"), saved to the topic's profile and given in the next brief.
- **Syllabus proposals:** a `propose_revision` tool whose change is shown as a card ("Add a unit on window functions?"); accepting applies it through the existing revision checks. The learner can also ask for more on a unit, or to skip one.

### Review
- Mastery per objective, computed from evidence and shown on the path, deciding how much retries count compared with first attempts.
- Review lessons that bring back weak or due objectives, by spaced repetition.

## Later

- **Notes back on:** `add_note` and the brief's notes section are commented out until learners can give feedback; the `notes` table is still there.
- **CI:** ruff, server tests, client tests and build; excluding billed live tests.
- **Wrong answer keys:** "Report a problem", correcting a key after an attempt, replacing a lesson; maybe a second model check when a lesson is written.
- **Model comparison:** run the same few topics on each model before changing a default.
- **Research beyond web search,** if checking facts in the run isn't enough (as in [learn](https://github.com/amosblomqvist/learn)): a separate `research` tool with its own, cheaper agent session, or a check after writing that verifies each key before the lesson is saved.
- **Engagement:** streaks, daily goals, XP.
