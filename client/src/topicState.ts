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
