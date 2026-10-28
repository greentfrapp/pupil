import { describe, expect, it } from 'vitest'
import type { Answer } from './api/lessons'
import { lessonStats } from './lessonStats'

const right: Answer = { response: { kind: 'bool', value: true }, correct: true }
const wrong: Answer = { response: { kind: 'bool', value: false }, correct: false }
const didntKnow: Answer = { response: null, correct: false }

describe('lessonStats', () => {
  it('counts the questions right, as a whole percent', () => {
    const stats = lessonStats({ a: right, b: wrong, c: right }, 0, 0)
    expect([stats.correct, stats.total, stats.accuracy]).toEqual([2, 3, 67])
  })

  it('counts a question the learner did not know as wrong', () => {
    expect(lessonStats({ a: right, b: didntKnow }, 0, 0).accuracy).toBe(50)
  })

  it('gives no accuracy for a lesson without questions', () => {
    expect(lessonStats({}, 0, 0).accuracy).toBe(0)
  })

  it('shows the time taken as minutes and seconds', () => {
    expect(lessonStats({}, 0, 125_400).time).toBe('2:05')
    expect(lessonStats({}, 1_000, 10_000).time).toBe('0:09')
  })
})
