<script setup lang="ts">
import { ref } from 'vue'
import type { LessonResponse, Matching } from '../../api/lessons'
import { shuffle } from '../../shuffle'
import { tileClass } from './styles'

const props = defineProps<{ question: Matching; disabled: boolean }>()
const response = defineModel<LessonResponse | null>({ required: true })

// Each side is shuffled on its own, so a pair's sides rarely line up.
const lefts = shuffle(props.question.pairs)
const rights = shuffle(props.question.pairs)

/** The left-hand item waiting for its match, if any. */
const selected = ref<string | null>(null)
/** Pair id of a left-hand side, to the pair id of the right-hand side matched with it. */
const matched = ref<Record<string, string>>({})

function pickLeft(id: string) {
  if (id in matched.value) {
    // Tapping a matched item undoes the match.
    const { [id]: _, ...rest } = matched.value
    matched.value = rest
    update()
  }
  selected.value = selected.value === id ? null : id
}

function pickRight(id: string) {
  if (selected.value === null) return
  // A right-hand side belongs to one match at a time.
  const kept = Object.entries(matched.value).filter(([, right]) => right !== id)
  matched.value = { ...Object.fromEntries(kept), [selected.value]: id }
  selected.value = null
  update()
}

function update() {
  const complete = Object.keys(matched.value).length === lefts.length
  response.value = complete ? { kind: 'matches', matches: { ...matched.value } } : null
}

/** The number shown on both sides of a match, so the learner can see what goes with what. */
function badge(leftId: string): number | null {
  const i = Object.keys(matched.value).indexOf(leftId)
  return i < 0 ? null : i + 1
}

function rightBadge(rightId: string): number | null {
  const left = Object.keys(matched.value).find((l) => matched.value[l] === rightId)
  return left === undefined ? null : badge(left)
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <p class="text-sm text-ink-500">Tap an item on the left, then its match on the right.</p>
    <div class="grid grid-cols-2 gap-2">
      <div class="flex flex-col gap-2">
        <button
          v-for="p in lefts"
          :key="p.id"
          :disabled="disabled"
          :class="[tileClass(selected === p.id), 'text-left']"
          @click="pickLeft(p.id)"
        >
          <span v-if="badge(p.id)" class="mr-2 font-semibold text-lake-600">{{ badge(p.id) }}</span>
          {{ p.left }}
        </button>
      </div>
      <div class="flex flex-col gap-2">
        <button
          v-for="p in rights"
          :key="p.id"
          :disabled="disabled || selected === null"
          :class="[tileClass(), 'text-left']"
          @click="pickRight(p.id)"
        >
          <span v-if="rightBadge(p.id)" class="mr-2 font-semibold text-lake-600">
            {{ rightBadge(p.id) }}
          </span>
          {{ p.right }}
        </button>
      </div>
    </div>
  </div>
</template>
