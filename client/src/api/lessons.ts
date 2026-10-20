// Mirrors pupil_server.api.lessons and pupil_server.learning.lesson. The lesson comes with its
// answers: the player grades each answer itself (see ../grading.ts), and the server stores the
// results it's sent.

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
}

export type Question = MultipleChoice | TrueFalse | Numeric | TextMatch

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

/** The learner's answer to one question, as the player graded it. */
export interface Answer {
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

async function failure(res: Response): Promise<Error> {
  const body = await res.json().catch(() => null)
  return new Error(body?.detail ?? `HTTP ${res.status}`)
}

/** The lesson with its answers, shuffled afresh, and the learner's attempts so far. */
export async function getLesson(
  id: string,
): Promise<{ lesson: Lesson; attempts: AttemptSummary[] }> {
  const res = await fetch(`/api/lessons/${id}`)
  if (!res.ok) throw await failure(res)
  return res.json()
}

/** Store a finished attempt: an answer for every question, as the player graded it. */
export async function submitAttempt(
  id: string,
  answers: Record<string, Answer>,
): Promise<AttemptSummary> {
  const res = await fetch(`/api/lessons/${id}/attempts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers }),
  })
  if (!res.ok) throw await failure(res)
  return res.json()
}
