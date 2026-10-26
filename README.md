# Pupil

A Duolingo-like app modeled after [amosblomqvist/learn](https://github.com/amosblomqvist/learn), based on the zone of proximal development.

> **Status: early.** Pupil runs on your own computer. Expect rough edges.

## How it works

1. **Say what you want to learn**, and answer four quick questions: why, how far you want to go, what you know already, and anything specific.
2. **Placement:** if you already know something, a short quiz finds where your knowledge runs out. Tap "I don't know" rather than guessing.
3. **Your plan:** The agent lays out units, each with a set number of lessons, and tells you why it's shaped that way.
4. **Lessons:** a mix of question types (multiple choice, fill in the blank, ordering, matching, and more), graded as you go, with an explanation for every answer. Each lesson follows up on what you got wrong.
5. **Finish, or go further:** once you've taken every lesson, Pupil can add units that go deeper.

The agent writes your next lesson in the background while you take the current one, so there's usually no waiting.

## Run it

You need:
- [Node.js](https://nodejs.org) 20+ and [pnpm](https://pnpm.io) 10
- [uv](https://docs.astral.sh/uv/) (it fetches the right Python for you)
- Claude Code or Codex, with a valid subscription

```sh
git clone https://github.com/greentfrapp/pupil.git
cd pupil
pnpm install
pnpm start
```

Then open http://127.0.0.1:8787.

**Your data** stays on your computer, in `~/Pupil/pupil.db`.

### Settings

Set these as environment variables, or in a `.env` file in the repo's root:

| Variable | Default | |
|---|---|---|
| `PUPIL_PORT` | `8787` | Where `pnpm start` serves |
| `PUPIL_HOST` | `127.0.0.1` | Keep this local: Pupil has no login |
| `PUPIL_DB_PATH` | `~/Pupil/pupil.db` | Where your topics and lessons are kept |
| `PUPIL_AGENT_BACKEND` | `claude` | `fake` runs without Claude, for development |
| `PUPIL_LOG_LEVEL` | `INFO` | |

## License

Copyright (C) 2026 greentfrapp. [AGPL-3.0-only](LICENSE).
