import { describe, expect, it } from 'vitest'
import { outOfOrder, shuffle } from './shuffle'

describe('shuffle', () => {
  it('keeps every item and leaves the original alone', () => {
    const items = [1, 2, 3, 4, 5]
    const shuffled = shuffle(items)
    expect([...shuffled].sort()).toEqual(items)
    expect(items).toEqual([1, 2, 3, 4, 5])
  })
})

describe('outOfOrder', () => {
  it('never returns the items in their original order', () => {
    for (let i = 0; i < 50; i++) {
      expect(outOfOrder([1, 2])).toEqual([2, 1])
      expect(outOfOrder([1, 2, 3])).not.toEqual([1, 2, 3])
    }
  })

  it('leaves a single item as it is', () => {
    expect(outOfOrder([1])).toEqual([1])
  })
})
