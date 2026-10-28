// Shared looks for answer inputs and setup choices: chunky tiles with a darker bottom edge
// they press down into, blue once picked, and green or red once an answer is checked.

import type { Mark } from '../../grading'

export const inputClass =
  'w-full rounded-2xl border-2 border-ink-200 bg-white px-4 py-3 text-lg focus:border-lake-400 focus:outline-none disabled:bg-ink-100'

const pressable =
  'border-2 shadow-[0_4px_0_var(--edge)] transition-[transform,box-shadow] duration-75 active:translate-y-1 active:shadow-none disabled:active:translate-y-0'

const MARKED: Record<Mark, string> = {
  right: 'border-leaf-400 bg-leaf-50 text-leaf-700 [--edge:var(--color-leaf-400)] disabled:opacity-100',
  wrong:
    'shake border-coral-400 bg-coral-50 text-coral-700 [--edge:var(--color-coral-400)] disabled:opacity-100',
  missed:
    'border-dashed border-leaf-400 bg-white text-leaf-700 [--edge:var(--color-leaf-200)] disabled:opacity-100',
}

/** How a tile looks: as checked if it has a mark, otherwise as picked or not. */
const look = (on: boolean, mark?: Mark) =>
  mark
    ? MARKED[mark]
    : on
      ? 'border-lake-300 bg-lake-50 text-lake-700 [--edge:var(--color-lake-300)]'
      : 'border-ink-200 bg-white hover:bg-ink-50 [--edge:var(--color-ink-200)]'

/** A large tappable choice, highlighted when picked. */
export const choiceClass = (on: boolean, mark?: Mark) => [
  'flex min-h-14 w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-lg',
  pressable,
  look(on, mark),
]

/** A small word or item tile, as in a word bank. */
export const tileClass = (on = false, mark?: Mark) => [
  'min-h-11 rounded-xl px-3 py-1.5 text-lg disabled:opacity-40',
  pressable,
  look(on, mark),
]

/** A typed answer's box, green or red once checked. */
export const typedClass = (mark?: Mark) => [
  inputClass,
  mark === 'right' && 'border-leaf-400! bg-leaf-50! text-leaf-700',
  mark === 'wrong' && 'shake border-coral-400! bg-coral-50! text-coral-700',
]
