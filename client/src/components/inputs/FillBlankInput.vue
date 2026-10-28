<script setup lang="ts">
import { computed, ref } from 'vue'
import { BLANK, type FillBlank, type LessonResponse } from '../../api/lessons'
import { shuffle } from '../../shuffle'
import { tileClass } from './styles'

const props = defineProps<{ question: FillBlank; disabled: boolean }>()
const response = defineModel<LessonResponse | null>({ required: true })

/** The text around the blanks: one more piece than there are blanks. */
const pieces = computed(() => props.question.text.split(BLANK))

// Typed answers, one per blank.
const typed = ref<string[]>(props.question.blanks.map(() => ''))

// With a word bank, each blank holds the index of the tile put in it, if any.
const tiles = shuffle(props.question.word_bank ?? [])
const placed = ref<(number | null)[]>(props.question.blanks.map(() => null))

function update() {
  const values = props.question.word_bank
    ? placed.value.map((t) => (t === null ? '' : tiles[t]))
    : typed.value.map((v) => v.trim())
  response.value = values.every((v) => v) ? { kind: 'blanks', values } : null
}

/** Put a tile in the first empty blank. */
function place(tile: number) {
  const empty = placed.value.indexOf(null)
  if (empty < 0) return
  placed.value[empty] = tile
  update()
}

function clear(blank: number) {
  placed.value[blank] = null
  update()
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <p class="font-mono text-lg leading-loose whitespace-pre-wrap">
      <template v-for="(piece, i) in pieces" :key="i">
        <span>{{ piece }}</span>
        <template v-if="i < question.blanks.length">
          <button
            v-if="question.word_bank"
            :disabled="disabled || placed[i] === null"
            class="mx-1 inline-block min-w-16 rounded-lg border-b-2 border-ink-400 px-2 align-baseline"
            @click="clear(i)"
          >
            {{ placed[i] === null ? ' ' : tiles[placed[i]] }}
          </button>
          <input
            v-else
            v-model="typed[i]"
            :disabled="disabled"
            class="mx-1 w-28 rounded-lg border-2 border-ink-200 px-2 align-baseline focus:border-lake-500 focus:outline-none"
            @input="update"
          />
        </template>
      </template>
    </p>
    <div v-if="question.word_bank" class="flex flex-wrap gap-2">
      <button
        v-for="(word, t) in tiles"
        :key="t"
        :disabled="disabled || placed.includes(t)"
        :class="tileClass()"
        @click="place(t)"
      >
        {{ word }}
      </button>
    </div>
  </div>
</template>
