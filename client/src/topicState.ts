// What a topic's screen shows, from the topic as the server last described it.

import type { Job, Topic } from './api/topics'

/**
 * start: before there's a plan, so placement, or waiting for the plan to be written.
 * plan: the plan, shown back with why it looks that way, until the first lesson is taken.
 * path: the units with their lessons, the next one highlighted.
 * finished: every lesson on the path taken, with the choice to go further.
 */
export type Screen = 'start' | 'plan' | 'path' | 'finished'

export function screen(topic: Topic): Screen {
  if (topic.finished) return 'finished'
  if (!topic.syllabus) return 'start'
  const started = topic.lessons.some((l) => l.purpose === 'lesson' && l.attempts > 0)
  return started ? 'path' : 'plan'
}

/**
 * What the learner can do next: take a lesson, wait for one, or ask for one again; or
 * nothing, once the path is finished.
 */
export type NextUp =
  | { kind: 'ready'; lessonId: string }
  | { kind: 'waiting'; job: Job }
  | { kind: 'stuck'; error: string | null }
  | { kind: 'done' }

export function nextUp(topic: Topic): NextUp {
  if (topic.next_lesson_id) return { kind: 'ready', lessonId: topic.next_lesson_id }
  const run = topic.last_run
  if (run?.state === 'running') return { kind: 'waiting', job: run.job }
  if (topic.finished) return { kind: 'done' }
  return { kind: 'stuck', error: run?.error ?? null }
}

/**
 * A stop on the path. done: taken. current: the lesson to take next. ready: written ahead,
 * after the current one. locked: not written yet.
 */
export type NodeState = 'done' | 'current' | 'ready' | 'locked'

export interface PathNode {
  /** Unique on the path, for keys and scrolling. */
  key: string
  lessonId: string | null
  title: string | null
  state: NodeState
  /** Where the learner is up to: the current lesson, or else the first stop still to write. */
  here: boolean
  /** The latest attempt's score, on a done lesson. */
  correct: number | null
  questions: number | null
}

export interface PathSection {
  unitId: string
  title: string
  summary: string
  nodes: PathNode[]
  done: number
}

/** The path's units, each with a node per stop, in learning order. */
export function pathSections(topic: Topic): PathSection[] {
  const lessons = new Map(topic.lessons.map((l) => [l.lesson_id, l]))
  const sections = topic.path.map((unit) => {
    const nodes: PathNode[] = []
    for (let i = 0; i < unit.stops; i++) {
      const lesson = lessons.get(unit.lesson_ids[i])
      const key = `${unit.unit_id}-${i}`
      if (!lesson) {
        nodes.push({
          key,
          lessonId: null,
          title: null,
          state: 'locked',
          here: false,
          correct: null,
          questions: null,
        })
        continue
      }
      const taken = lesson.attempts > 0
      const state: NodeState = taken
        ? 'done'
        : lesson.lesson_id === topic.next_lesson_id
          ? 'current'
          : 'ready'
      nodes.push({
        key,
        lessonId: lesson.lesson_id,
        title: lesson.title,
        state,
        here: state === 'current',
        correct: taken ? lesson.latest_correct : null,
        questions: taken ? lesson.questions : null,
      })
    }
    return {
      unitId: unit.unit_id,
      title: unit.title,
      summary: unit.summary,
      nodes,
      done: nodes.filter((n) => n.state === 'done').length,
    }
  })
  const all = sections.flatMap((s) => s.nodes)
  if (!all.some((n) => n.here)) {
    const upcoming = all.find((n) => n.state === 'locked')
    if (upcoming) upcoming.here = true
  }
  return sections
}
