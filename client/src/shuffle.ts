// Display order for questions whose answer is an arrangement: the server can't shuffle these,
// because for an ordering question the stored order is the answer.

/** A shuffled copy of `items`. */
export function shuffle<T>(items: readonly T[], random: () => number = Math.random): T[] {
  const copy = [...items]
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

/** A shuffled copy of `items` that is never already in their original order, so an ordering
 * question can't start out solved. */
export function outOfOrder<T>(items: readonly T[], random: () => number = Math.random): T[] {
  if (items.length < 2) return [...items]
  for (;;) {
    const shuffled = shuffle(items, random)
    if (shuffled.some((item, i) => item !== items[i])) return shuffled
  }
}
