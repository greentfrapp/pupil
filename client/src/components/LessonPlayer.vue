<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  checkAnswer,
  getLesson,
  submitAttempt,
  type Attempt,
  type AttemptSummary,
  type Check,
  type LessonResponse,
  type LessonView,
  type QuestionView,
} from '../api/lessons'

const props = defineProps<{ lessonId: string }>()
const emit = defineEmits<{ close: [] }>()

const lesson = ref<LessonView | null>(null)
const attempts = ref<AttemptSummary[]>([])
const error = ref<string | null>(null)
const busy = ref(false)

// One run through the lesson. Quitting part-way keeps nothing: the attempt is only submitted
// at the end.
const index = ref(0)
const responses = ref<Record<string, LessonResponse>>({})
const feedback = ref<Check | null>(null)
const result = ref<Attempt | null>(null)

// What the learner has entered for the current question, in the form each input edits.
const picked = ref<string[]>([])
const bool = ref<boolean | null>(null)
const typed = ref('')

const item = computed(() => lesson.value?.items[index.value])
const question = computed(() =>
  item.value && item.value.kind !== 'teach_card' ? item.value : null,
)
const isLast = computed(() => index.value === (lesson.value?.items.length ?? 0) - 1)
const progress = computed(() => {
  const total = lesson.value?.items.length ?? 1
  const done = index.value + (feedback.value || !question.value ? 1 : 0)
  return result.value ? 100 : (done / total) * 100
})
/** A placement lesson can't be retried, so once taken it only shows how it went. */
const taken = computed(
  () => !result.value && lesson.value?.purpose === 'placement' && attempts.value.length > 0,
)

async function load() {
  error.value = null
  lesson.value = null
  result.value = null
  index.value = 0
  responses.value = {}
  feedback.value = null
  clearInputs()
  try {
    const loaded = await getLesson(props.lessonId)
    lesson.value = loaded.lesson
    attempts.value = loaded.attempts
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(load)

function clearInputs() {
  picked.value = []
  bool.value = null
  typed.value = ''
}

function toggle(q: QuestionView, optionId: string) {
  if (!q.multiple) picked.value = [optionId]
  else if (picked.value.includes(optionId))
    picked.value = picked.value.filter((id) => id !== optionId)
  else picked.value = [...picked.value, optionId]
}

/** The learner's answer to the current question, or null until they've given one. */
const response = computed<LessonResponse | null>(() => {
  const q = question.value
  if (!q) return null
  const raw = typed.value.trim()
  switch (q.kind) {
    case 'multiple_choice':
      return picked.value.length ? { kind: 'choice', option_ids: picked.value } : null
    case 'true_false':
      return bool.value === null ? null : { kind: 'bool', value: bool.value }
    case 'numeric':
      return raw && Number.isFinite(Number(raw)) ? { kind: 'number', value: Number(raw) } : null
    case 'text_match':
      return raw ? { kind: 'text', text: raw } : null
  }
  return null
})

async function check() {
  const q = question.value
  const r = response.value
  if (!q || !r || busy.value || feedback.value) return
  busy.value = true
  error.value = null
  try {
    feedback.value = await checkAnswer(props.lessonId, q.id, r)
    responses.value[q.id] = r
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

async function next() {
  if (busy.value || result.value) return
  if (!isLast.value) {
    index.value++
    feedback.value = null
    clearInputs()
    return
  }
  busy.value = true
  error.value = null
  try {
    result.value = await submitAttempt(props.lessonId, responses.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

/** Enter checks the answer, then moves on. */
function onEnter() {
  if (!lesson.value || result.value || taken.value) return
  if (feedback.value || !question.value) next()
  else check()
}

function describe(q: QuestionView, r: LessonResponse | null): string {
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
  if (!lesson.value || !result.value) return []
  const byId = new Map(lesson.value.items.map((i) => [i.id, i]))
  return result.value.results.map((r) => {
    const q = byId.get(r.question_id) as QuestionView
    return { ...r, prompt: q.prompt, given: describe(q, r.response) }
  })
})

const inputClass =
  'w-full rounded-xl border-2 border-gray-200 px-3 py-2 text-lg focus:border-blue-500 focus:outline-none disabled:bg-gray-50'
const choiceClass = (on: boolean) => [
  'flex w-full items-center gap-3 rounded-xl border-2 px-4 py-3 text-left text-lg',
  on ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:bg-gray-50',
]
const footerStyle = computed(() => {
  if (!feedback.value) return 'border-gray-100'
  return feedback.value.correct ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
})
const buttonClass =
  'rounded-xl px-6 py-3 text-lg font-semibold text-white disabled:opacity-40 bg-blue-600 hover:bg-blue-700'
</script>

<template>
  <div class="fixed inset-0 z-10 flex flex-col bg-white" @keydown.enter.prevent="onEnter">
    <header class="flex items-center gap-4 px-4 py-4">
      <button
        class="text-2xl text-gray-400 hover:text-gray-700"
        aria-label="Quit the lesson"
        @click="emit('close')"
      >
        ✕
      </button>
      <div class="h-3 flex-1 overflow-hidden rounded-full bg-gray-200">
        <div
          class="h-full rounded-full bg-green-500 transition-all"
          :style="{ width: `${progress}%` }"
        />
      </div>
    </header>

    <main class="mx-auto flex w-full max-w-xl flex-1 flex-col gap-5 overflow-y-auto px-4 py-6">
      <p v-if="!lesson && error" class="text-red-600">{{ error }}</p>
      <p v-else-if="!lesson" class="text-gray-500">Loading…</p>

      <!-- A placement lesson that has already been taken -->
      <template v-else-if="taken">
        <h2 class="text-2xl font-bold">{{ lesson.title }}</h2>
        <p class="text-lg">
          You've already taken this placement and got
          <strong>{{ attempts[0].correct }} of {{ attempts[0].total }}</strong> right.
        </p>
      </template>

      <!-- Results, once the lesson is finished -->
      <template v-else-if="result">
        <h2 class="text-2xl font-bold">Lesson complete!</h2>
        <p class="text-lg">
          You got <strong>{{ result.correct }} of {{ result.total }}</strong> right<span
            v-if="result.number > 1"
          >
            on attempt {{ result.number }}</span
          >.
        </p>
        <ol class="flex flex-col gap-2">
          <li
            v-for="r in results"
            :key="r.question_id"
            class="rounded-xl border-2 border-gray-100 px-4 py-3"
          >
            <p class="font-medium">
              <span :class="r.correct ? 'text-green-600' : 'text-red-600'">
                {{ r.correct ? '✓' : '✗' }}
              </span>
              {{ r.prompt }}
            </p>
            <p v-if="!r.correct" class="text-sm text-gray-600">
              You said {{ r.given }}; the answer is {{ r.answer }}.
            </p>
          </li>
        </ol>
      </template>

      <!-- A teach card -->
      <template v-else-if="item && item.kind === 'teach_card'">
        <p class="text-sm font-semibold tracking-wide text-blue-600 uppercase">New idea</p>
        <h2 class="text-2xl font-bold">{{ item.title }}</h2>
        <p class="text-lg whitespace-pre-wrap">{{ item.text }}</p>
      </template>

      <!-- A question -->
      <template v-else-if="question">
        <p class="text-xl whitespace-pre-wrap">{{ question.prompt }}</p>

        <div v-if="question.kind === 'multiple_choice'" class="flex flex-col gap-2">
          <p v-if="question.multiple" class="text-sm text-gray-500">Pick every correct answer.</p>
          <button
            v-for="o in question.options ?? []"
            :key="o.id"
            :disabled="!!feedback"
            :class="choiceClass(picked.includes(o.id))"
            @click="toggle(question, o.id)"
          >
            {{ o.text }}
          </button>
        </div>

        <div v-else-if="question.kind === 'true_false'" class="flex gap-2">
          <button
            v-for="value in [true, false]"
            :key="String(value)"
            :disabled="!!feedback"
            :class="[choiceClass(bool === value), 'justify-center']"
            @click="bool = value"
          >
            {{ value ? 'True' : 'False' }}
          </button>
        </div>

        <div v-else-if="question.kind === 'numeric'" class="flex items-center gap-2">
          <input
            v-model="typed"
            inputmode="decimal"
            :disabled="!!feedback"
            :class="inputClass"
            autofocus
          />
          <span v-if="question.unit" class="text-lg text-gray-600">{{ question.unit }}</span>
        </div>

        <input v-else v-model="typed" :disabled="!!feedback" :class="inputClass" autofocus />
      </template>
    </main>

    <footer
      v-if="lesson && !taken"
      :class="['border-t-2 px-4 py-5', footerStyle]"
    >
      <div class="mx-auto flex max-w-xl flex-col gap-3">
        <div v-if="feedback">
          <p :class="['text-xl font-bold', feedback.correct ? 'text-green-700' : 'text-red-700']">
            {{ feedback.correct ? 'Correct!' : 'Not quite' }}
          </p>
          <p v-if="!feedback.correct" class="font-medium">Answer: {{ feedback.answer }}</p>
          <p class="text-gray-700">{{ feedback.explanation }}</p>
        </div>
        <p v-if="error" class="text-red-600">{{ error }}</p>

        <div v-if="result" class="flex justify-end gap-2">
          <button
            v-if="lesson.purpose === 'lesson'"
            class="rounded-xl border-2 border-gray-200 px-6 py-3 text-lg font-semibold hover:bg-gray-50"
            @click="load"
          >
            Retry
          </button>
          <button :class="buttonClass" @click="emit('close')">Done</button>
        </div>
        <button
          v-else-if="question && !feedback"
          :disabled="!response || busy"
          :class="[buttonClass, 'self-end']"
          @click="check"
        >
          Check
        </button>
        <button v-else :disabled="busy" :class="[buttonClass, 'self-end']" @click="next">
          {{ isLast ? (busy ? 'Finishing…' : 'Finish') : 'Continue' }}
        </button>
      </div>
    </footer>
  </div>
</template>
