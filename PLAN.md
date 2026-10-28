# Plan

## Next: a Duolingo-style UI

Closer to Duolingo in look and feel, the path and the lesson, mobile-first. Pupil uses the
design language (chunky 3D buttons, a bold rounded font, a winding path, celebratory
feedback) but none of Duolingo's assets: no owl, font, brand colours or sounds. No mascot or
gamification yet. Three branches, in order:

**`ui-foundation`**
- [x] Design tokens: Pupil's own bright palette, large radii, an off-white background, and the Nunito font bundled locally.
- [x] Shared components: 3D buttons, pressable choice tiles, a thick progress bar, and a small set of SVG icons.
- [x] Home and intake restyled, in a phone-width column centred on desktop.

**`ui-path`**
- [x] The topic page as a winding path of round lesson nodes under coloured unit banners: done, current (with a START bubble), ready and locked.
- [x] Tapping a node shows its title and score with Start or Review; the path ends in a trophy that opens Go further.
- [x] Waiting and failed runs show at the current node.

**`ui-lesson`**
- [x] After Check, the tiles show the right and wrong answers.
- [x] Bold green and red feedback panels, motion between questions, and a shake on a wrong answer. (Sound effects left out for now.)
- [x] A lesson-complete screen with accuracy, time and questions, and the answers to review.

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
