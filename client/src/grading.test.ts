import { describe, expect, it } from 'vitest'
import type {
  FillBlank,
  Matching,
  MultipleChoice,
  Numeric,
  Ordering,
  TextMatch,
  TrueFalse,
} from './api/lessons'
import { answerText, grade, responseText } from './grading'

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

function fillBlank(text: string, answers: string[][], caseSensitive = false): FillBlank {
  return {
    ...basics,
    kind: 'fill_blank',
    id: 'q',
    text,
    blanks: answers.map((accepted) => ({ accepted })),
    word_bank: null,
    case_sensitive: caseSensitive,
  }
}

function ordering(...texts: string[]): Ordering {
  return {
    ...basics,
    kind: 'ordering',
    id: 'q',
    sequence: texts.map((t, i) => ({ id: String(i), text: t })),
  }
}

function matching(...pairs: [string, string][]): Matching {
  return {
    ...basics,
    kind: 'matching',
    id: 'q',
    pairs: pairs.map(([left, right], i) => ({ id: String(i), left, right })),
  }
}

const picks = (...ids: string[]) => ({ kind: 'choice' as const, option_ids: ids })
const number = (value: number) => ({ kind: 'number' as const, value })
const text = (value: string) => ({ kind: 'text' as const, text: value })
const blanks = (...values: string[]) => ({ kind: 'blanks' as const, values })
const order = (...ids: string[]) => ({ kind: 'order' as const, item_ids: ids })
const matched = (matches: Record<string, string>) => ({ kind: 'matches' as const, matches })

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

  it('needs every blank filled with one of its accepted answers', () => {
    const q = fillBlank('___ = ___ + 1', [['x'], ['y', 'Y1']])
    expect(grade(q, blanks(' X ', 'y1'))).toBe(true) // spacing and case don't matter
    expect(grade(q, blanks('x', 'z'))).toBe(false)
    expect(grade(q, blanks('y', 'x'))).toBe(false) // each blank has its own answers
    expect(grade(q, blanks('x'))).toBe(false)
  })

  it('keeps case in blanks when the question is case sensitive', () => {
    const q = fillBlank('print(___)', [['None']], true)
    expect(grade(q, blanks('None'))).toBe(true)
    expect(grade(q, blanks('none'))).toBe(false)
  })

  it('needs the items in exactly the right order', () => {
    const q = ordering('boil', 'steep', 'pour')
    expect(grade(q, order('0', '1', '2'))).toBe(true)
    expect(grade(q, order('1', '0', '2'))).toBe(false)
    expect(grade(q, order('0', '1'))).toBe(false)
  })

  it('needs every pair matched correctly', () => {
    const q = matching(['cat', 'chat'], ['dog', 'chien'])
    expect(grade(q, matched({ 0: '0', 1: '1' }))).toBe(true)
    expect(grade(q, matched({ 0: '1', 1: '0' }))).toBe(false)
    expect(grade(q, matched({ 0: '0' }))).toBe(false)
  })
})

describe('responseText', () => {
  it('names what was picked, not its ids', () => {
    expect(responseText(choice(['a']), picks('c', 'a'))).toBe('C, A')
    expect(responseText(ordering('boil', 'pour'), order('1', '0'))).toBe('pour → boil')
    expect(responseText(matching(['cat', 'chat'], ['dog', 'chien']), matched({ 0: '1', 1: '0' })))
      .toBe('cat → chien; dog → chat')
  })

  it('gives typed answers as typed', () => {
    expect(responseText(numeric(3, 0, 'cm'), number(4))).toBe('4 cm')
    expect(responseText(fillBlank('___ ___', [['a'], ['b']]), blanks('x', 'y'))).toBe('x, y')
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

  it('fills each blank with its first accepted answer', () => {
    const q = fillBlank('for ___ in ______(3):', [['i', 'x'], ['range']])
    expect(answerText(q)).toBe('for i in range(3):')
  })

  it('lists items in order, and pairs', () => {
    expect(answerText(ordering('boil', 'pour'))).toBe('boil → pour')
    expect(answerText(matching(['cat', 'chat'], ['dog', 'chien']))).toBe('cat → chat; dog → chien')
  })
})
