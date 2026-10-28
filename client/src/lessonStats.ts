// What the lesson-complete screen shows about one run through a lesson.

import type { Answer } from './api/lessons'

export interface LessonStats {
  correct: number
  total: number
  /** Whole percent right, 0 to 100. */
  accuracy: number
  /** From the first item to the last, as m:ss. */
  time: string
}

export function lessonStats(
  answers: Record<string, Answer>,
  startedAt: number,
  finishedAt: number,
): LessonStats {
  const all = Object.values(answers)
  const correct = all.filter((a) => a.correct).length
  const total = all.length
  const seconds = Math.max(0, Math.round((finishedAt - startedAt) / 1000))
  const time = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
  return { correct, total, accuracy: total ? Math.round((correct / total) * 100) : 0, time }
}
