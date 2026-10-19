// Mirrors pupil_server.api.quizzes and the learner's view in pupil_server.learning.quiz.

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

export interface QuizView {
  id: string
  title: string
  purpose: 'placement' | 'checkpoint'
  questions: QuestionView[]
}

export type QuizResponse =
  | { kind: 'choice'; option_ids: string[] }
  | { kind: 'bool'; value: boolean }
  | { kind: 'number'; value: number }
  | { kind: 'text'; text: string }

export interface Result {
  question_id: string
  correct: boolean
  response: QuizResponse | null
  explanation: string | null
}

export interface Attempt {
  attempt_id: string
  correct: number
  total: number
  results: Result[]
}

async function failure(res: Response): Promise<Error> {
  const body = await res.json().catch(() => null)
  return new Error(body?.detail ?? `HTTP ${res.status}`)
}

/** The quiz without its answers, and the learner's results once they have taken it. */
export async function getQuiz(id: string): Promise<{ quiz: QuizView; attempt: Attempt | null }> {
  const res = await fetch(`/api/quizzes/${id}`)
  if (!res.ok) throw await failure(res)
  return res.json()
}

export async function submitAnswers(
  id: string,
  responses: Record<string, QuizResponse>,
): Promise<Attempt> {
  const res = await fetch(`/api/quizzes/${id}/attempts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ responses }),
  })
  if (!res.ok) throw await failure(res)
  return res.json()
}
