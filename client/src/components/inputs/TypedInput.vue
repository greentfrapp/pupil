<script setup lang="ts">
import { ref, watch } from 'vue'
import type { LessonResponse, Numeric, TextMatch } from '../../api/lessons'
import { answerText, type Mark } from '../../grading'
import { typedClass } from './styles'

const props = defineProps<{
  question: Numeric | TextMatch
  disabled: boolean
  marks?: Record<string, Mark> | null
}>()
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
  <div class="flex flex-col gap-2">
    <div class="flex items-center gap-2">
      <input
        v-model="typed"
        :inputmode="question.kind === 'numeric' ? 'decimal' : 'text'"
        :disabled="disabled"
        :class="typedClass(marks?.answer)"
        autofocus
      />
      <span v-if="question.kind === 'numeric' && question.unit" class="text-lg text-ink-600">
        {{ question.unit }}
      </span>
    </div>
    <!-- The right answer, under a wrong one or an empty box -->
    <p
      v-if="marks?.answer === 'wrong' || marks?.answer === 'missed'"
      class="self-start rounded-2xl border-2 border-dashed border-leaf-400 bg-white px-4 py-2 text-lg text-leaf-700"
    >
      <span class="sr-only">Correct answer: </span>{{ answerText(question) }}
    </p>
  </div>
</template>
