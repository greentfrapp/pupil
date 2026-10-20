import { describe, expect, it } from 'vitest'
import type { MultipleChoice, Numeric, TextMatch, TrueFalse } from './api/lessons'
import { answerText, grade } from './grading'

const basics = { prompt: 'p', objective_ids: [], difficulty: 1, explanation: 'Because.' }

function choice(correct: string[], multiple = false): MultipleChoice {
  return {
    ...basics,
    kind: 'multiple_choice',
    id: 'q',
    options: ['a', 'b', 'c'].map((id) => ({ id, text: id.toUpperCase() })),
    correct,
    multiple,
    keep_option_order: false,
  }
}

function trueFalse(answer: boolean): TrueFalse {
  return { ...basics, kind: 'true_false', id: 'q', answer }
}

function numeric(answer: number, tolerance = 0, unit: string | null = null): Numeric {
  return { ...basics, kind: 'numeric', id: 'q', answer, tolerance, unit }
}

function textMatch(accepted: string[], caseSensitive = false): TextMatch {
  return { ...basics, kind: 'text_match', id: 'q', accepted, case_sensitive: caseSensitive }
}

const picks = (...ids: string[]) => ({ kind: 'choice' as const, option_ids: ids })
const number = (value: number) => ({ kind: 'number' as const, value })
const text = (value: string) => ({ kind: 'text' as const, text: value })

describe('grade', () => {
  it('needs exactly the right option for a single-answer question', () => {
    const q = choice(['b'])
    expect(grade(q, picks('b'))).toBe(true)
    expect(grade(q, picks('a'))).toBe(false)
    expect(grade(q, picks('a', 'b'))).toBe(false)
  })

  it('needs every right option, and no others, for a multiple-answer question', () => {
    const q = choice(['a', 'c'], true)
    expect(grade(q, picks('c', 'a'))).toBe(true)
    expect(grade(q, picks('a'))).toBe(false) // a subset is not enough
    expect(grade(q, picks('a', 'b', 'c'))).toBe(false)
  })

  it('grades true/false', () => {
    expect(grade(trueFalse(true), { kind: 'bool', value: true })).toBe(true)
    expect(grade(trueFalse(true), { kind: 'bool', value: false })).toBe(false)
  })

  it('counts a number exactly at the tolerance as right', () => {
    const q = numeric(10, 0.5)
    expect(grade(q, number(10.5))).toBe(true)
    expect(grade(q, number(9.5))).toBe(true)
    expect(grade(q, number(10.51))).toBe(false)
    expect(grade(numeric(32), number(32))).toBe(true)
    expect(grade(numeric(32), number(32.01))).toBe(false)
  })

  it('ignores spacing and case in text', () => {
    expect(grade(textMatch(['def']), text('  DEF '))).toBe(true)
    expect(grade(textMatch(['def']), text('define'))).toBe(false)
    expect(grade(textMatch(['for  loop']), text('For\tLoop'))).toBe(true)
  })

  it('keeps case when the question is case sensitive', () => {
    expect(grade(textMatch(['None'], true), text(' None'))).toBe(true)
    expect(grade(textMatch(['None'], true), text('none'))).toBe(false)
  })

  it('refuses a response of the wrong kind', () => {
    expect(() => grade(trueFalse(true), text('yes'))).toThrow('needs a bool response')
  })
})

describe('answerText', () => {
  it('lists the right options in their order', () => {
    expect(answerText(choice(['c', 'a'], true))).toBe('A, C')
  })

  it('says True or False', () => {
    expect(answerText(trueFalse(false))).toBe('False')
  })

  it('gives a number with its unit and tolerance', () => {
    expect(answerText(numeric(3))).toBe('3')
    expect(answerText(numeric(2.5, 0.1, 'cm'))).toBe('2.5 cm (± 0.1)')
  })

  it('gives the first accepted text', () => {
    expect(answerText(textMatch(['def', 'DEF']))).toBe('def')
  })
})
