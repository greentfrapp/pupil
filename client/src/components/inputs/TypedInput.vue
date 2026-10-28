<script setup lang="ts">
import { ref, watch } from 'vue'
import type { LessonResponse, Numeric, TextMatch } from '../../api/lessons'
import { inputClass } from './styles'

const props = defineProps<{ question: Numeric | TextMatch; disabled: boolean }>()
const response = defineModel<LessonResponse | null>({ required: true })

const typed = ref('')

watch(typed, (value) => {
  const raw = value.trim()
  if (props.question.kind === 'numeric') {
    response.value =
      raw && Number.isFinite(Number(raw)) ? { kind: 'number', value: Number(raw) } : null
  } else {
    response.value = raw ? { kind: 'text', text: raw } : null
  }
})
</script>

<template>
  <div class="flex items-center gap-2">
    <input
      v-model="typed"
      :inputmode="question.kind === 'numeric' ? 'decimal' : 'text'"
      :disabled="disabled"
      :class="inputClass"
      autofocus
    />
    <span v-if="question.kind === 'numeric' && question.unit" class="text-lg text-ink-600">
      {{ question.unit }}
    </span>
  </div>
</template>
