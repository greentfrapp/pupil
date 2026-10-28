import { describe, expect, it } from 'vitest'
import type { LessonSummary, RunStatus, Topic } from './api/topics'
import { nextUp, pathSections, screen } from './topicState'

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
    finished: false,
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

  it('is finished once every lesson on the path is taken', () => {
    const lessons = [lesson('lesson', 1)]
    expect(screen(topic({ syllabus, lessons, finished: true }))).toBe('finished')
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

  it('is done when the path is finished, unless a run is adding to it', () => {
    expect(nextUp(topic({ finished: true, last_run: run('done') }))).toEqual({ kind: 'done' })
    const extending = { job: 'extend' as const, state: 'running' as const, error: null }
    expect(nextUp(topic({ finished: true, last_run: extending }))).toEqual({
      kind: 'waiting',
      job: 'extend',
    })
  })

  it('is stuck after a failed run, or when nothing is going', () => {
    const failed = topic({ last_run: run('failed', 'the run was cut off') })
    expect(nextUp(failed)).toEqual({ kind: 'stuck', error: 'the run was cut off' })
    expect(nextUp(topic({ last_run: run('done') }))).toEqual({ kind: 'stuck', error: null })
  })
})

describe('pathSections', () => {
  function taken(id: string, correct: number): LessonSummary {
    return { ...lesson('lesson', 1), lesson_id: id, title: id, questions: 5, latest_correct: correct }
  }
  function untaken(id: string): LessonSummary {
    return { ...lesson('lesson', 0), lesson_id: id, title: id, questions: 5 }
  }
  const unit = (id: string, stops: number, lesson_ids: string[]) => ({
    unit_id: id,
    title: `Unit ${id}`,
    summary: 's',
    stops,
    lesson_ids,
  })

  it('marks lessons done, current, ready and locked, with scores on the done ones', () => {
    const t = topic({
      syllabus,
      lessons: [lesson('placement', 1), taken('a', 4), untaken('b'), untaken('c')],
      path: [unit('u1', 2, ['a', 'b']), unit('u2', 3, ['c'])],
      next_lesson_id: 'b',
    })
    const sections = pathSections(t)
    const nodes = sections.flatMap((s) => s.nodes)
    expect(nodes.map((n) => [n.lessonId, n.state])).toEqual([
      ['a', 'done'],
      ['b', 'current'],
      ['c', 'ready'],
      [null, 'locked'],
      [null, 'locked'],
    ])
    expect([nodes[0].correct, nodes[0].questions]).toEqual([4, 5])
    expect([nodes[1].correct, nodes[1].questions]).toEqual([null, null])
    expect(sections.map((s) => s.done)).toEqual([1, 0])
  })

  it('leaves the placement lesson off the path', () => {
    const t = topic({ syllabus, lessons: [lesson('placement', 1)], path: [unit('u1', 1, [])] })
    expect(pathSections(t).flatMap((s) => s.nodes.map((n) => n.lessonId))).toEqual([null])
  })

  it('puts the learner at the current lesson', () => {
    const t = topic({
      syllabus,
      lessons: [taken('a', 5), untaken('b')],
      path: [unit('u1', 3, ['a', 'b'])],
      next_lesson_id: 'b',
    })
    expect(pathSections(t)[0].nodes.map((n) => n.here)).toEqual([false, true, false])
  })

  it('puts the learner at the first stop still to write when no lesson is waiting', () => {
    const t = topic({
      syllabus,
      lessons: [taken('a', 3)],
      path: [unit('u1', 1, ['a']), unit('u2', 2, [])],
    })
    const sections = pathSections(t)
    expect(sections.map((s) => s.nodes.map((n) => n.here))).toEqual([[false], [true, false]])
    expect(sections[1].nodes[0].state).toBe('locked')
  })

  it('has no one place to be once every lesson is taken', () => {
    const t = topic({
      syllabus,
      lessons: [taken('a', 3), taken('b', 5)],
      path: [unit('u1', 2, ['a', 'b'])],
      finished: true,
    })
    const nodes = pathSections(t)[0].nodes
    expect(nodes.map((n) => n.state)).toEqual(['done', 'done'])
    expect(nodes.some((n) => n.here)).toBe(false)
  })
})
