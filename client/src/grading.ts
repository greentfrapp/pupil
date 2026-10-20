// Grading happens here, in the lesson player, by code and never by a model. The server doesn't
// grade again: it stores the results it's sent, along with the learner's responses.

import type { LessonResponse, Question } from './api/lessons'

/** Whether `response` answers `question` correctly. */
export function grade(question: Question, response: LessonResponse): boolean {
  switch (question.kind) {
    case 'multiple_choice': {
      const chosen = expect(question, response, 'choice').option_ids
      const correct = new Set(question.correct)
      return new Set(chosen).size === correct.size && chosen.every((id) => correct.has(id))
    }
    case 'true_false':
      return expect(question, response, 'bool').value === question.answer
    case 'numeric':
      return Math.abs(expect(question, response, 'number').value - question.answer) <=
        question.tolerance
    case 'text_match': {
      const given = normalize(expect(question, response, 'text').text, question.case_sensitive)
      return question.accepted.some((a) => normalize(a, question.case_sensitive) === given)
    }
  }
}

/** The correct answer, as the learner sees it after answering. */
export function answerText(question: Question): string {
  switch (question.kind) {
    case 'multiple_choice':
      return question.options
        .filter((o) => question.correct.includes(o.id))
        .map((o) => o.text)
        .join(', ')
    case 'true_false':
      return question.answer ? 'True' : 'False'
    case 'numeric': {
      let text = String(question.answer)
      if (question.unit) text += ` ${question.unit}`
      if (question.tolerance) text += ` (± ${question.tolerance})`
      return text
    }
    case 'text_match':
      return question.accepted[0]
  }
}

/** Spacing never matters; case only matters when the question says so. */
function normalize(text: string, caseSensitive: boolean): string {
  const collapsed = text.trim().split(/\s+/).join(' ')
  return caseSensitive ? collapsed : collapsed.toLowerCase()
}

function expect<K extends LessonResponse['kind']>(
  question: Question,
  response: LessonResponse,
  kind: K,
): Extract<LessonResponse, { kind: K }> {
  if (response.kind !== kind) {
    throw new Error(`question ${question.id} (${question.kind}) needs a ${kind} response`)
  }
  return response as Extract<LessonResponse, { kind: K }>
}
