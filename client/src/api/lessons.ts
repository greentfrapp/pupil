// Mirrors pupil_server.api.lessons and the learner's view in pupil_server.learning.lesson.

export type Kind = 'multiple_choice' | 'true_false' | 'numeric' | 'text_match'

export interface Option {
  id: string
  text: string
}

export interface QuestionView {
  kind: Kind
  id: string
  prompt: string
  options: Option[] | null
  multiple: boolean | null
  unit: string | null
}

export interface TeachCardView {
  kind: 'teach_card'
  id: string
  title: string
  text: string
}

export type ItemView = QuestionView | TeachCardView

export interface LessonView {
  id: string
  title: string
  purpose: 'placement' | 'lesson'
  items: ItemView[]
}

export type LessonResponse =
  | { kind: 'choice'; option_ids: string[] }
  | { kind: 'bool'; value: boolean }
  | { kind: 'number'; value: number }
  | { kind: 'text'; text: string }

export interface AttemptSummary {
  attempt_id: string
  number: number
  correct: number
  total: number
  submitted_at: string
}

export interface Check {
  correct: boolean
  answer: string
  explanation: string
}

export interface Result {
  question_id: string
  correct: boolean
  response: LessonResponse | null
  answer: string
  explanation: string
}

export interface Attempt {
  attempt_id: string
  number: number
  correct: number
  total: number
  results: Result[]
}

async function failure(res: Response): Promise<Error> {
  const body = await res.json().catch(() => null)
  return new Error(body?.detail ?? `HTTP ${res.status}`)
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await failure(res)
  return res.json()
}

/** The lesson without its answers, shuffled afresh, and the learner's attempts so far. */
export async function getLesson(
  id: string,
): Promise<{ lesson: LessonView; attempts: AttemptSummary[] }> {
  const res = await fetch(`/api/lessons/${id}`)
  if (!res.ok) throw await failure(res)
  return res.json()
}

/** Grade one answer as it's given; nothing is stored until the attempt is submitted. */
export function checkAnswer(
  id: string,
  questionId: string,
  response: LessonResponse,
): Promise<Check> {
  return post(`/api/lessons/${id}/check`, { question_id: questionId, response })
}

export function submitAttempt(
  id: string,
  responses: Record<string, LessonResponse>,
): Promise<Attempt> {
  return post(`/api/lessons/${id}/attempts`, { responses })
}
