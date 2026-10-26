# Plan

## Before release

- **Codex backend:** a second agent backend next to `claude`, so Pupil isn't tied to one model. `AgentBackend` (`agents/base.py`) is the interface; the README already lists Codex.

## Next steps

### Steering
- **After each lesson:** "Too easy / About right / Too hard", plus optional chips ("More examples", "More real-world"), saved to the topic's profile and given in the next brief.
- **Syllabus proposals:** a `propose_revision` tool whose change is shown as a card ("Add a unit on window functions?"); accepting applies it through the existing revision checks. The learner can also ask for more on a unit, or to skip one.

### Review
- Mastery per objective, computed from evidence and shown on the path, deciding how much retries count compared with first attempts.
- Review lessons that bring back weak or due objectives, by spaced repetition.

## Known issues

- **Lessons written ahead can repeat questions:** the brief lists an untaken lesson by title only, so the next one can ask the same thing (John Keel in the Discworld session). Give the brief its questions, or have the run read it.
- **A run cut off by a restart** isn't run again until the learner finishes a lesson or taps Try again, losing the lesson written ahead once. Prepare every topic at startup.
- **Explanations may run long,** up to about 210 characters.

## Later

- **Notes back on:** `add_note` and the brief's notes section are commented out until learners can give feedback; the `notes` table is still there.
- **CI:** ruff, server tests, client tests and build; excluding billed live tests.
- **Wrong answer keys:** "Report a problem", correcting a key after an attempt, replacing a lesson; maybe a second model check when a lesson is written.
- **Engagement:** streaks, daily goals, XP.
