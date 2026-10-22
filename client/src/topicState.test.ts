import { describe, expect, it } from 'vitest'
import type { LessonSummary, RunStatus, Topic } from './api/topics'
import { nextUp, screen } from './topicState'

const syllabus = { id: 's', topic: 'SQL', goal: 'g', rationale: 'r', revision: 1 }

function lesson(purpose: LessonSummary['purpose'], attempts: number): LessonSummary {
  return {
    lesson_id: `${purpose}-${attempts}`,
    title: 't',
    purpose,
    questions: 3,
    attempts,
    latest_correct: attempts ? 2 : null,
  }
}

function topic(fields: Partial<Topic> = {}): Topic {
  return {
    id: 'top',
    request: 'SQL',
    profile: { why: 'work', depth: 'working', level: 'basics', specific: null },
    created_at: '2026-01-01T00:00:00Z',
    syllabus: null,
    lessons: [],
    path: [],
    next_lesson_id: null,
    last_run: null,
    ...fields,
  }
}

describe('screen', () => {
  it('starts with placement, or waiting for the plan', () => {
    expect(screen(topic({ lessons: [lesson('placement', 1)] }))).toBe('start')
  })

  it('shows the plan until a lesson from it is taken', () => {
    const lessons = [lesson('placement', 1), lesson('lesson', 0)]
    expect(screen(topic({ syllabus, lessons }))).toBe('plan')
  })

  it('shows the path once a lesson from the plan is taken', () => {
    const lessons = [lesson('lesson', 1), lesson('lesson', 0)]
    expect(screen(topic({ syllabus, lessons }))).toBe('path')
  })
})

describe('nextUp', () => {
  const run = (state: RunStatus['state'], error: string | null = null): RunStatus => ({
    job: 'next_lesson',
    state,
    error,
  })

  it('is the lesson waiting to be taken, even while a run goes', () => {
    const t = topic({ next_lesson_id: 'les_1', last_run: run('running') })
    expect(nextUp(t)).toEqual({ kind: 'ready', lessonId: 'les_1' })
  })

  it('waits for a run that is going', () => {
    expect(nextUp(topic({ last_run: run('running') }))).toEqual({
      kind: 'waiting',
      job: 'next_lesson',
    })
  })

  it('is stuck after a failed run, or when nothing is going', () => {
    const failed = topic({ last_run: run('failed', 'the run was cut off') })
    expect(nextUp(failed)).toEqual({ kind: 'stuck', error: 'the run was cut off' })
    expect(nextUp(topic({ last_run: run('done') }))).toEqual({ kind: 'stuck', error: null })
  })
})
