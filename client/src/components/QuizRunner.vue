<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  getQuiz,
  submitAnswers,
  type Attempt,
  type QuestionView,
  type QuizResponse,
  type QuizView,
} from '../api/quizzes'

const props = defineProps<{ quizId: string }>()
const emit = defineEmits<{ close: []; submitted: [attempt: Attempt] }>()

const quiz = ref<QuizView | null>(null)
const attempt = ref<Attempt | null>(null)
const error = ref<string | null>(null)
const submitting = ref(false)
const index = ref(0)

// What the learner has entered so far, by question id, in the form each input edits.
const choices = ref<Record<string, string[]>>({})
const bools = ref<Record<string, boolean>>({})
const texts = ref<Record<string, string>>({})

const question = computed(() => quiz.value?.questions[index.value])
const isLast = computed(() => index.value === (quiz.value?.questions.length ?? 0) - 1)

onMounted(async () => {
  try {
    const loaded = await getQuiz(props.quizId)
    quiz.value = loaded.quiz
    attempt.value = loaded.attempt
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})

function toggle(q: QuestionView, optionId: string) {
  const picked = choices.value[q.id] ?? []
  if (!q.multiple) choices.value[q.id] = [optionId]
  else if (picked.includes(optionId)) choices.value[q.id] = picked.filter((id) => id !== optionId)
  else choices.value[q.id] = [...picked, optionId]
}

/** The learner's answer to a question, or null if they left it blank. */
function response(q: QuestionView): QuizResponse | null {
  switch (q.kind) {
    case 'multiple_choice': {
      const picked = choices.value[q.id] ?? []
      return picked.length ? { kind: 'choice', option_ids: picked } : null
    }
    case 'true_false':
      return q.id in bools.value ? { kind: 'bool', value: bools.value[q.id] } : null
    case 'numeric': {
      const raw = (texts.value[q.id] ?? '').trim()
      return raw && Number.isFinite(Number(raw)) ? { kind: 'number', value: Number(raw) } : null
    }
    case 'text_match': {
      const raw = (texts.value[q.id] ?? '').trim()
      return raw ? { kind: 'text', text: raw } : null
    }
  }
}

async function submit() {
  if (!quiz.value || submitting.value) return
  const responses: Record<string, QuizResponse> = {}
  for (const q of quiz.value.questions) {
    const r = response(q)
    if (r) responses[q.id] = r
  }
  submitting.value = true
  error.value = null
  try {
    attempt.value = await submitAnswers(props.quizId, responses)
    emit('submitted', attempt.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    submitting.value = false
  }
}

function describe(q: QuestionView, r: QuizResponse | null): string {
  if (!r) return 'Skipped'
  switch (r.kind) {
    case 'choice':
      return r.option_ids.map((id) => q.options?.find((o) => o.id === id)?.text ?? id).join(', ')
    case 'bool':
      return r.value ? 'True' : 'False'
    case 'number':
      return q.unit ? `${r.value} ${q.unit}` : String(r.value)
    case 'text':
      return r.text
  }
}

const results = computed(() => {
  if (!quiz.value || !attempt.value) return []
  const byId = new Map(quiz.value.questions.map((q) => [q.id, q]))
  return attempt.value.results.map((r) => {
    const q = byId.get(r.question_id)!
    return { ...r, prompt: q.prompt, answer: describe(q, r.response) }
  })
})

const inputClass =
  'w-full rounded-md border border-gray-300 px-2 py-1.5 focus:border-blue-500 focus:outline-none'
</script>

<template>
  <div class="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
    <section
      class="flex max-h-full w-full max-w-lg flex-col gap-4 overflow-y-auto rounded-lg bg-white p-5 shadow-xl"
    >
      <header class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-lg font-semibold">{{ quiz?.title ?? 'Quiz' }}</h2>
          <p v-if="quiz && !attempt" class="text-sm text-gray-500">
            Question {{ index + 1 }} of {{ quiz.questions.length }}
          </p>
        </div>
        <button class="text-gray-500 hover:text-gray-900" aria-label="Close" @click="emit('close')">
          ✕
        </button>
      </header>

      <p v-if="error" class="text-red-600">{{ error }}</p>
      <p v-else-if="!quiz" class="text-gray-500">Loading…</p>

      <!-- Results, once the quiz has been answered -->
      <template v-else-if="attempt">
        <p class="text-lg">
          You got <strong>{{ attempt.correct }} of {{ attempt.total }}</strong> right.
        </p>
        <ol class="flex flex-col gap-3">
          <li v-for="r in results" :key="r.question_id" class="rounded-md border border-gray-200 p-3">
            <p class="font-medium">
              <span :class="r.correct ? 'text-green-700' : 'text-red-600'">
                {{ r.correct ? '✓' : '✗' }}
              </span>
              {{ r.prompt }}
            </p>
            <p class="text-sm text-gray-600">Your answer: {{ r.answer }}</p>
            <p v-if="r.explanation" class="mt-1 text-sm">{{ r.explanation }}</p>
          </li>
        </ol>
        <button
          class="self-end rounded-md bg-blue-600 px-4 py-1.5 text-white hover:bg-blue-700"
          @click="emit('close')"
        >
          Back to chat
        </button>
      </template>

      <!-- One question at a time -->
      <template v-else-if="question">
        <p class="text-lg whitespace-pre-wrap">{{ question.prompt }}</p>

        <div v-if="question.kind === 'multiple_choice'" class="flex flex-col gap-2">
          <p v-if="question.multiple" class="text-sm text-gray-500">Pick every correct answer.</p>
          <label
            v-for="o in question.options ?? []"
            :key="o.id"
            class="flex cursor-pointer items-center gap-2 rounded-md border border-gray-300 px-3 py-2 hover:bg-gray-50"
          >
            <input
              :type="question.multiple ? 'checkbox' : 'radio'"
              :name="question.id"
              :checked="(choices[question.id] ?? []).includes(o.id)"
              @change="toggle(question, o.id)"
            />
            {{ o.text }}
          </label>
        </div>

        <div v-else-if="question.kind === 'true_false'" class="flex gap-2">
          <button
            v-for="value in [true, false]"
            :key="String(value)"
            :class="[
              'flex-1 rounded-md border px-3 py-2',
              bools[question.id] === value
                ? 'border-blue-600 bg-blue-50'
                : 'border-gray-300 hover:bg-gray-50',
            ]"
            @click="bools[question.id] = value"
          >
            {{ value ? 'True' : 'False' }}
          </button>
        </div>

        <div v-else-if="question.kind === 'numeric'" class="flex items-center gap-2">
          <input v-model="texts[question.id]" inputmode="decimal" :class="inputClass" />
          <span v-if="question.unit" class="text-gray-600">{{ question.unit }}</span>
        </div>

        <input v-else v-model="texts[question.id]" :class="inputClass" />

        <footer class="flex justify-between">
          <button
            :disabled="index === 0"
            class="rounded-md border border-gray-300 px-3 py-1.5 hover:bg-gray-50 disabled:opacity-50"
            @click="index--"
          >
            Back
          </button>
          <button
            v-if="!isLast"
            class="rounded-md bg-blue-600 px-4 py-1.5 text-white hover:bg-blue-700"
            @click="index++"
          >
            Next
          </button>
          <button
            v-else
            :disabled="submitting"
            class="rounded-md bg-blue-600 px-4 py-1.5 text-white hover:bg-blue-700 disabled:opacity-50"
            @click="submit"
          >
            {{ submitting ? 'Submitting…' : 'Submit' }}
          </button>
        </footer>
      </template>
    </section>
  </div>
</template>
