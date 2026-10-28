<script setup lang="ts">
import { ref } from 'vue'
import type { LessonResponse, Ordering } from '../../api/lessons'
import { outOfOrder } from '../../shuffle'
import { tileClass } from './styles'

const props = defineProps<{ question: Ordering; disabled: boolean }>()
const response = defineModel<LessonResponse | null>({ required: true })

/** The items to pick from, never already in the right order. */
const pool = outOfOrder(props.question.sequence)
/** Item ids, in the order the learner has tapped them. */
const placed = ref<string[]>([])

function toggle(id: string) {
  placed.value = placed.value.includes(id)
    ? placed.value.filter((p) => p !== id)
    : [...placed.value, id]
  response.value =
    placed.value.length === pool.length ? { kind: 'order', item_ids: placed.value } : null
}

const text = (id: string) => pool.find((o) => o.id === id)?.text
</script>

<template>
  <div class="flex flex-col gap-4">
    <p class="text-sm text-ink-500">Tap the items in order. Tap one again to take it back.</p>
    <ol class="flex min-h-14 flex-col gap-2 rounded-xl border-2 border-dashed border-ink-200 p-2">
      <li v-for="(id, i) in placed" :key="id">
        <button
          :disabled="disabled"
          :class="[tileClass(true), 'w-full text-left']"
          @click="toggle(id)"
        >
          <span class="mr-2 text-ink-400">{{ i + 1 }}.</span>{{ text(id) }}
        </button>
      </li>
    </ol>
    <div class="flex flex-wrap gap-2">
      <button
        v-for="o in pool"
        :key="o.id"
        :disabled="disabled || placed.includes(o.id)"
        :class="tileClass()"
        @click="toggle(o.id)"
      >
        {{ o.text }}
      </button>
    </div>
  </div>
</template>
