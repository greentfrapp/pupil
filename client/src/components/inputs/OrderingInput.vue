<script setup lang="ts">
import { computed, ref } from 'vue'
import type { LessonResponse, Ordering } from '../../api/lessons'
import { outOfOrder } from '../../shuffle'
import type { Mark } from '../../grading'
import { tileClass } from './styles'

const props = defineProps<{
  question: Ordering
  disabled: boolean
  /** How each place in the order did, once checked. */
  marks?: Record<string, Mark> | null
}>()
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

/** Whether, once checked, any place is wrong or the learner didn't know, so the order is shown. */
const showOrder = computed(
  () => !!props.marks && Object.values(props.marks).some((m) => m !== 'right'),
)
</script>

<template>
  <div class="flex flex-col gap-4">
    <p v-if="!marks" class="text-sm text-ink-500">
      Tap the items in order. Tap one again to take it back.
    </p>
    <ol
      v-if="!marks || placed.length"
      class="flex min-h-14 flex-col gap-2 rounded-xl border-2 border-dashed border-ink-200 p-2"
    >
      <li v-for="(id, i) in placed" :key="id">
        <button
          :disabled="disabled"
          :class="[tileClass(true, marks?.[i]), 'w-full text-left']"
          @click="toggle(id)"
        >
          <span class="mr-2 text-ink-400">{{ i + 1 }}.</span>{{ text(id) }}
        </button>
      </li>
    </ol>
    <div v-if="!marks" class="flex flex-wrap gap-2">
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
    <!-- Once checked, the right order, unless the learner had it -->
    <div v-if="showOrder" class="flex flex-col gap-2">
      <p class="text-sm font-extrabold tracking-wide text-leaf-700 uppercase">Correct order</p>
      <ol class="flex flex-col gap-2">
        <li v-for="(o, i) in question.sequence" :key="o.id">
          <span :class="[tileClass(false, 'missed'), 'flex w-full items-center']">
            <span class="mr-2 text-ink-400">{{ i + 1 }}.</span>{{ o.text }}
          </span>
        </li>
      </ol>
    </div>
  </div>
</template>
