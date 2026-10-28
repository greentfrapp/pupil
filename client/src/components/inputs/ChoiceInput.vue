<script setup lang="ts">
import { ref } from 'vue'
import type { LessonResponse, MultipleChoice } from '../../api/lessons'
import type { Mark } from '../../grading'
import { choiceClass } from './styles'

const props = defineProps<{
  question: MultipleChoice
  disabled: boolean
  /** How each option did, once checked. */
  marks?: Record<string, Mark> | null
}>()
const response = defineModel<LessonResponse | null>({ required: true })

const picked = ref<string[]>([])

function toggle(optionId: string) {
  if (!props.question.multiple) picked.value = [optionId]
  else if (picked.value.includes(optionId))
    picked.value = picked.value.filter((id) => id !== optionId)
  else picked.value = [...picked.value, optionId]
  response.value = picked.value.length ? { kind: 'choice', option_ids: picked.value } : null
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <p v-if="question.multiple" class="text-sm text-ink-500">Pick every correct answer.</p>
    <button
      v-for="o in question.options"
      :key="o.id"
      :disabled="disabled"
      :class="choiceClass(picked.includes(o.id), marks?.[o.id])"
      @click="toggle(o.id)"
    >
      {{ o.text }}
    </button>
  </div>
</template>
