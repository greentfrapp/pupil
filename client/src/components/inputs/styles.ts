// Shared looks for answer inputs and setup choices: bordered tiles, yellow once picked, and green
// or red once an answer is checked.

import type { Mark } from '../../grading'

export const inputClass =
  'w-full rounded-2xl border-2 border-ink-200 bg-white px-4 py-3 text-lg focus:border-sun-400 focus:outline-none disabled:bg-ink-100'

const MARKED: Record<Mark, string> = {
  right: 'border-leaf-400 bg-leaf-50 text-leaf-700 disabled:opacity-100',
  wrong: 'shake border-coral-400 bg-coral-50 text-coral-700 disabled:opacity-100',
  missed: 'border-dashed border-leaf-400 bg-white text-leaf-700 disabled:opacity-100',
}

/** How a tile looks: as checked if it has a mark, otherwise as picked or not. */
const look = (on: boolean, mark?: Mark) =>
  mark
    ? MARKED[mark]
    : on
      ? 'border-sun-400 bg-sun-50 text-sun-900'
      : 'border-ink-200 bg-white hover:bg-ink-50'

/** A large tappable choice, highlighted when picked. */
export const choiceClass = (on: boolean, mark?: Mark) => [
  'flex min-h-14 w-full items-center gap-3 rounded-2xl border-2 px-4 py-3 text-left text-lg',
  look(on, mark),
]

/** A small word or item tile, as in a word bank. */
export const tileClass = (on = false, mark?: Mark) => [
  'min-h-11 rounded-xl border-2 px-3 py-1.5 text-lg disabled:opacity-40',
  look(on, mark),
]

/** A typed answer's box, green or red once checked. */
export const typedClass = (mark?: Mark) => [
  inputClass,
  mark === 'right' && 'border-leaf-400! bg-leaf-50! text-leaf-700',
  mark === 'wrong' && 'shake border-coral-400! bg-coral-50! text-coral-700',
]
