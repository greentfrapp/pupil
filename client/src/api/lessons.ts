// Mirrors pupil_server.api.lessons and pupil_server.learning.lesson. The lesson comes with its
// answers: the player grades each answer itself (see ../grading.ts), and the server stores the
// results it's sent.

import { getJson, postJson } from './http'

export interface Option {
  id: string
  text: string
}

interface QuestionBase {
  id: string
  prompt: string
  objective_ids: string[]
  difficulty: number
  explanation: string
}

export interface MultipleChoice extends QuestionBase {
  kind: 'multiple_choice'
  options: Option[]
  correct: string[]
  multiple: boolean
  keep_option_order: boolean
}

export interface TrueFalse extends QuestionBase {
  kind: 'true_false'
  answer: boolean
}

export interface Numeric extends QuestionBase {
  kind: 'numeric'
  answer: number
  tolerance: number
  unit: string | null
}

export interface TextMatch extends QuestionBase {
  kind: 'text_match'
  accepted: string[]
  case_sensitive: boolean
  /** Grade strictly: only spacing, and case unless case_sensitive, are ignored. */
  exact: boolean
}

export interface FillBlank extends QuestionBase {
  kind: 'fill_blank'
  /** The text to complete, with ___ (three or more underscores) where each blank goes. */
  text: string
  blanks: { accepted: string[] }[]
  /** Words to pick from instead of typing, each used at most once. */
  word_bank: string[] | null
  case_sensitive: boolean
  /** Grade strictly: only spacing, and case unless case_sensitive, are ignored. */
  exact: boolean
}

export interface Ordering extends QuestionBase {
  kind: 'ordering'
  /** The items in the correct order; the player shuffles them. */
  sequence: Option[]
}

export interface Matching extends QuestionBase {
  kind: 'matching'
  /** The correct pairs; the player shuffles each side separately. */
  pairs: { id: string; left: string; right: string }[]
}

export type Question =
  | MultipleChoice
  | TrueFalse
  | Numeric
  | TextMatch
  | FillBlank
  | Ordering
  | Matching

/** Where a blank goes in a fill_blank question's text. */
export const BLANK = /_{3,}/

export interface TeachCard {
  kind: 'teach_card'
  id: string
  title: string
  text: string
}

export type Item = Question | TeachCard

export interface Lesson {
  id: string
  title: string
  purpose: 'placement' | 'lesson'
  syllabus_id: string | null
  keep_order: boolean
  items: Item[]
}

export type LessonResponse =
  | { kind: 'choice'; option_ids: string[] }
  | { kind: 'bool'; value: boolean }
  | { kind: 'number'; value: number }
  | { kind: 'text'; text: string }
  | { kind: 'blanks'; values: string[] }
  | { kind: 'order'; item_ids: string[] }
  /** Each pair's id, to the id of the pair whose right-hand side was matched with its left. */
  | { kind: 'matches'; matches: Record<string, string> }

/** The learner's answer to one question, as the player graded it. */
export interface Answer {
  /** Null if the learner said they didn't know. */
  response: LessonResponse | null
  correct: boolean
}

export interface AttemptSummary {
  attempt_id: string
  number: number
  correct: number
  total: number
  submitted_at: string
}

/** The lesson with its answers, shuffled afresh, and the learner's attempts so far. */
export async function getLesson(
  id: string,
): Promise<{ lesson: Lesson; attempts: AttemptSummary[] }> {
  return getJson(`/api/lessons/${id}`)
}

/** Store a finished attempt: an answer for every question, as the player graded it. */
export async function submitAttempt(
  id: string,
  answers: Record<string, Answer>,
): Promise<AttemptSummary> {
  return postJson(`/api/lessons/${id}/attempts`, { answers })
}
