// Grading happens here, in the lesson player, by code and never by a model. The server doesn't
// grade again: it stores the results it's sent, along with the learner's responses.

import { BLANK, type LessonResponse, type Question } from './api/lessons'

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
      const given = expect(question, response, 'text').text
      return matches(given, question.accepted, question.case_sensitive)
    }
    case 'fill_blank': {
      const values = expect(question, response, 'blanks').values
      return (
        values.length === question.blanks.length &&
        question.blanks.every((b, i) => matches(values[i], b.accepted, question.case_sensitive))
      )
    }
    case 'ordering': {
      const ids = expect(question, response, 'order').item_ids
      return (
        ids.length === question.sequence.length &&
        question.sequence.every((o, i) => ids[i] === o.id)
      )
    }
    case 'matching': {
      const given = expect(question, response, 'matches').matches
      return (
        Object.keys(given).length === question.pairs.length &&
        question.pairs.every((p) => given[p.id] === p.id)
      )
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
    case 'fill_blank': {
      let blank = 0
      const fill = () => question.blanks[blank++].accepted[0]
      return question.text.replace(new RegExp(BLANK, 'g'), fill)
    }
    case 'ordering':
      return question.sequence.map((o) => o.text).join(' → ')
    case 'matching':
      return question.pairs.map((p) => `${p.left} → ${p.right}`).join('; ')
  }
}

/** What the learner answered, in words. */
export function responseText(question: Question, response: LessonResponse): string {
  switch (response.kind) {
    case 'choice': {
      const options = question.kind === 'multiple_choice' ? question.options : []
      return response.option_ids.map((id) => textOf(options, id)).join(', ')
    }
    case 'bool':
      return response.value ? 'True' : 'False'
    case 'number':
      return question.kind === 'numeric' && question.unit
        ? `${response.value} ${question.unit}`
        : String(response.value)
    case 'text':
      return response.text
    case 'blanks':
      return response.values.join(', ')
    case 'order': {
      const items = question.kind === 'ordering' ? question.sequence : []
      return response.item_ids.map((id) => textOf(items, id)).join(' → ')
    }
    case 'matches': {
      const pairs = question.kind === 'matching' ? question.pairs : []
      const side = (id: string, which: 'left' | 'right') =>
        pairs.find((p) => p.id === id)?.[which] ?? id
      return Object.entries(response.matches)
        .map(([left, right]) => `${side(left, 'left')} → ${side(right, 'right')}`)
        .join('; ')
    }
  }
}

function textOf(items: { id: string; text: string }[], id: string): string {
  return items.find((i) => i.id === id)?.text ?? id
}

function matches(given: string, accepted: string[], caseSensitive: boolean): boolean {
  const normalized = normalize(given, caseSensitive)
  return accepted.some((a) => normalize(a, caseSensitive) === normalized)
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
