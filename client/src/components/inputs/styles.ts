// Shared looks for the lesson player's answer inputs.

export const inputClass =
  'w-full rounded-xl border-2 border-gray-200 px-3 py-2 text-lg focus:border-blue-500 focus:outline-none disabled:bg-gray-50'

/** A large tappable choice, highlighted when picked. */
export const choiceClass = (on: boolean) => [
  'flex w-full items-center gap-3 rounded-xl border-2 px-4 py-3 text-left text-lg',
  on ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:bg-gray-50',
]

/** A small word or item tile, as in a word bank. */
export const tileClass = (on = false) => [
  'rounded-xl border-2 px-3 py-1.5 text-lg disabled:opacity-40',
  on ? 'border-blue-500 bg-blue-50' : 'border-gray-200 bg-white hover:bg-gray-50',
]
