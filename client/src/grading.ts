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
      return matches(given, question.accepted, question)
    }
    case 'fill_blank': {
      const values = expect(question, response, 'blanks').values
      return (
        values.length === question.blanks.length &&
        question.blanks.every((b, i) => matches(values[i], b.accepted, question))
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

interface MatchRules {
  case_sensitive: boolean
  exact: boolean
}

/** Whether `given` counts as one of the `accepted` answers.
 *
 * Spacing never matters, and case only when the question says so. Unless the question is
 * exact, neither do punctuation, accents, a leading "the", "a" or "an", or British against
 * American spelling; and an answer of six or more characters, with no digits, may be one typo
 * off. */
function matches(given: string, accepted: string[], rules: MatchRules): boolean {
  const normalize = (text: string) => {
    const collapsed = text.trim().split(/\s+/).join(' ')
    const cased = rules.case_sensitive ? collapsed : collapsed.toLowerCase()
    return rules.exact ? cased : loosen(cased)
  }
  const response = normalize(given)
  return accepted.some((a) => {
    const answer = normalize(a)
    if (answer === response) return true
    const typoAllowed = !rules.exact && answer.length >= 6 && !/\d/.test(answer)
    return typoAllowed && withinOneEdit(answer, response)
  })
}

/** Drops what a typed answer shouldn't be marked wrong for: accents, punctuation, a leading
 * article and British spellings (each word is put in its American form). */
function loosen(text: string): string {
  const words = text
    .normalize('NFD')
    .replace(/\p{M}/gu, '') // accents
    .replace(/['‘’`"“”]/g, '') // T'Phon is TPhon
    .replace(/[\p{P}\p{S}]/gu, ' ') // Cut-Me-Own-Throat is Cut Me Own Throat
    .split(/\s+/)
    .filter(Boolean)
  if (words.length > 1 && ['the', 'a', 'an'].includes(words[0].toLowerCase())) words.shift()
  return words.map(americanSpelling).join(' ')
}

/** The American spelling of a British one: colour, centre, organise, analyse, defence,
 * catalogue, encyclopaedia, travelled. Other words come back as they were. */
function americanSpelling(word: string): string {
  if (word.length >= 6) word = word.replace(/our(s|ed|ing|able|ite|ites)?$/i, 'or$1')
  if (word.length >= 7) word = word.replace(/ogue(s)?$/i, 'og$1')
  return word
    .replace(/([bgt])re(s|d)?$/i, '$1er$2')
    .replace(/is(e|es|ed|ing|ation|ations)$/i, 'iz$1')
    .replace(/ys(e|es|ed|ing)$/i, 'yz$1')
    .replace(/ence(s)?$/i, 'ense$1')
    .replace(/ll(ed|ing|er|ers)$/i, 'l$1')
    .replace(/(?<=.)ae/gi, 'e')
}

/** Whether one insertion, deletion, substitution or swap of neighbours turns `a` into `b`. */
function withinOneEdit(a: string, b: string): boolean {
  if (Math.abs(a.length - b.length) > 1) return false
  let i = 0
  while (i < a.length && i < b.length && a[i] === b[i]) i++
  if (a.length === b.length) {
    if (a.slice(i + 1) === b.slice(i + 1)) return true // substitution
    return a[i] === b[i + 1] && a[i + 1] === b[i] && a.slice(i + 2) === b.slice(i + 2) // swap
  }
  const [shorter, longer] = a.length < b.length ? [a, b] : [b, a]
  return shorter.slice(i) === longer.slice(i + 1) // insertion or deletion
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
