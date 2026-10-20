<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  getLesson,
  RequestFailed,
  submitAttempt,
  type Answer,
  type AttemptSummary,
  type Lesson,
  type LessonResponse,
  type Question,
} from '../api/lessons'
import { answerText, grade, responseText } from '../grading'
import ChoiceInput from './inputs/ChoiceInput.vue'
import FillBlankInput from './inputs/FillBlankInput.vue'
import MatchingInput from './inputs/MatchingInput.vue'
import OrderingInput from './inputs/OrderingInput.vue'
import TrueFalseInput from './inputs/TrueFalseInput.vue'
import TypedInput from './inputs/TypedInput.vue'

const props = defineProps<{ lessonId: string }>()
const emit = defineEmits<{ close: [] }>()

const lesson = ref<Lesson | null>(null)
const attempts = ref<AttemptSummary[]>([])
const error = ref<string | null>(null)
const busy = ref(false)

// One run through the lesson. Quitting part-way keeps nothing: the attempt is only submitted
// at the end.
const index = ref(0)
const answers = ref<Record<string, Answer>>({})
const finished = ref(false)

// Saving the finished attempt. The results come from the answers graded here, so they show
// whether or not saving works.
const saved = ref<AttemptSummary | null>(null)
const saveProblem = ref<{ message: string; canRetry: boolean } | null>(null)

/** The learner's answer to the current question, or null until they've given a whole one. */
const response = ref<LessonResponse | null>(null)
/** Counts runs through the lesson, so a retry starts every input afresh. */
const run = ref(0)

const item = computed(() => lesson.value?.items[index.value])
const question = computed(() =>
  item.value && item.value.kind !== 'teach_card' ? item.value : null,
)
/** How the learner did on the current question, once they've checked their answer. */
const feedback = computed(() => {
  const q = question.value
  const answer = q && answers.value[q.id]
  if (finished.value || !q || !answer) return null
  return { correct: answer.correct, answer: answerText(q), explanation: q.explanation }
})
const isLast = computed(() => index.value === (lesson.value?.items.length ?? 0) - 1)
const progress = computed(() => {
  const total = lesson.value?.items.length ?? 1
  const done = index.value + (feedback.value || !question.value ? 1 : 0)
  return finished.value ? 100 : (done / total) * 100
})
/** A placement lesson can't be retried, so once taken it only shows how it went. */
const taken = computed(
  () => !finished.value && lesson.value?.purpose === 'placement' && attempts.value.length > 0,
)

async function load() {
  error.value = null
  lesson.value = null
  finished.value = false
  saved.value = null
  saveProblem.value = null
  index.value = 0
  answers.value = {}
  response.value = null
  run.value++
  try {
    const loaded = await getLesson(props.lessonId)
    lesson.value = loaded.lesson
    attempts.value = loaded.attempts
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(load)

function check() {
  const q = question.value
  const r = response.value
  if (!q || !r || feedback.value) return
  answers.value[q.id] = { response: r, correct: grade(q, r) }
}

function next() {
  if (finished.value) return
  if (isLast.value) {
    finished.value = true
    save()
    return
  }
  index.value++
  response.value = null
}

async function save() {
  if (busy.value || saved.value) return
  busy.value = true
  saveProblem.value = null
  try {
    saved.value = await submitAttempt(props.lessonId, answers.value)
  } catch (e) {
    saveProblem.value = problem(e)
  } finally {
    busy.value = false
  }
}

/** What to tell the learner when saving fails, and whether trying again could help. */
function problem(e: unknown): { message: string; canRetry: boolean } {
  if (e instanceof RequestFailed && e.status === 409) {
    const message = "You've already taken this placement, so this attempt wasn't saved."
    return { message, canRetry: false }
  }
  const message = `This attempt couldn't be saved: ${e instanceof Error ? e.message : e}`
  // The server refused it (4xx), so sending it again would be refused again. Anything else,
  // such as the server being unreachable, may pass on another try.
  const refused = e instanceof RequestFailed && e.status < 500
  return { message, canRetry: !refused }
}

/** Enter checks the answer, then moves on. */
function onEnter() {
  if (!lesson.value || finished.value || taken.value) return
  if (feedback.value || !question.value) next()
  else check()
}

/** Every question, in the order taken, with how the learner did. */
const results = computed(() => {
  if (!lesson.value || !finished.value) return []
  return lesson.value.items
    .filter((i): i is Question => i.kind !== 'teach_card')
    .map((q) => {
      const answer = answers.value[q.id]
      return {
        id: q.id,
        prompt: q.prompt,
        correct: answer.correct,
        given: answer.response ? responseText(q, answer.response) : 'Skipped',
        answer: answerText(q),
      }
    })
})

const footerStyle = computed(() => {
  if (!feedback.value) return 'border-gray-100'
  return feedback.value.correct ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
})
const secondaryClass =
  'rounded-xl border-2 border-gray-200 px-6 py-3 text-lg font-semibold hover:bg-gray-50 disabled:opacity-40'
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
      <template v-else-if="finished">
        <h2 class="text-2xl font-bold">Lesson complete!</h2>
        <p class="text-lg">
          You got
          <strong>{{ results.filter((r) => r.correct).length }} of {{ results.length }}</strong>
          right<span v-if="saved && saved.number > 1"> on attempt {{ saved.number }}</span>.
        </p>
        <ol class="flex flex-col gap-2">
          <li
            v-for="r in results"
            :key="r.id"
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

        <!-- Keyed by run and question, so each starts empty, and is shuffled afresh -->
        <ChoiceInput
          v-if="question.kind === 'multiple_choice'"
          :key="`${run}-${question.id}`"
          v-model="response"
          :question="question"
          :disabled="!!feedback"
        />
        <TrueFalseInput
          v-else-if="question.kind === 'true_false'"
          :key="`${run}-${question.id}`"
          v-model="response"
          :disabled="!!feedback"
        />
        <FillBlankInput
          v-else-if="question.kind === 'fill_blank'"
          :key="`${run}-${question.id}`"
          v-model="response"
          :question="question"
          :disabled="!!feedback"
        />
        <OrderingInput
          v-else-if="question.kind === 'ordering'"
          :key="`${run}-${question.id}`"
          v-model="response"
          :question="question"
          :disabled="!!feedback"
        />
        <MatchingInput
          v-else-if="question.kind === 'matching'"
          :key="`${run}-${question.id}`"
          v-model="response"
          :question="question"
          :disabled="!!feedback"
        />
        <TypedInput
          v-else
          :key="`${run}-${question.id}`"
          v-model="response"
          :question="question"
          :disabled="!!feedback"
        />
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
        <template v-if="finished">
          <p v-if="busy" class="text-gray-500">Saving…</p>
          <p v-else-if="saveProblem" class="text-red-600">{{ saveProblem.message }}</p>
          <div class="flex justify-end gap-2">
            <button
              v-if="saveProblem?.canRetry"
              :disabled="busy"
              :class="secondaryClass"
              @click="save"
            >
              Try saving again
            </button>
            <button
              v-if="lesson.purpose === 'lesson'"
              :disabled="busy"
              :class="secondaryClass"
              @click="load"
            >
              Retry lesson
            </button>
            <button :class="buttonClass" @click="emit('close')">Done</button>
          </div>
        </template>
        <button
          v-else-if="question && !feedback"
          :disabled="!response"
          :class="[buttonClass, 'self-end']"
          @click="check"
        >
          Check
        </button>
        <button v-else :class="[buttonClass, 'self-end']" @click="next">
          {{ isLast ? 'Finish' : 'Continue' }}
        </button>
      </div>
    </footer>
  </div>
</template>
