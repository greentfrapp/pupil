// Shared looks for answer inputs and setup choices: chunky tiles with a darker bottom edge
// they press down into, blue once picked.

export const inputClass =
  'w-full rounded-2xl border-2 border-ink-200 bg-white px-4 py-3 text-lg focus:border-lake-400 focus:outline-none disabled:bg-ink-100'

const pressable =
  'border-2 shadow-[0_4px_0_var(--edge)] transition-[transform,box-shadow] duration-75 active:translate-y-1 active:shadow-none disabled:active:translate-y-0'

const picked = (on: boolean) =>
  on
    ? 'border-lake-300 bg-lake-50 text-lake-700 [--edge:var(--color-lake-300)]'
    : 'border-ink-200 bg-white hover:bg-ink-50 [--edge:var(--color-ink-200)]'

/** A large tappable choice, highlighted when picked. */
export const choiceClass = (on: boolean) => [
  'flex min-h-14 w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-lg',
  pressable,
  picked(on),
]

/** A small word or item tile, as in a word bank. */
export const tileClass = (on = false) => [
  'min-h-11 rounded-xl px-3 py-1.5 text-lg disabled:opacity-40',
  pressable,
  picked(on),
]
