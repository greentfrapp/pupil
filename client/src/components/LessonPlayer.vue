<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RequestFailed } from '../api/http'
import {
  getLesson,
  submitAttempt,
  type Answer,
  type AttemptSummary,
  type Lesson,
  type LessonResponse,
  type Question,
} from '../api/lessons'
import { answerText, feedbackFor, grade, responseText } from '../grading'
import { renderInline, renderMarkdown } from '../markdown'
import ChoiceInput from './inputs/ChoiceInput.vue'
import FillBlankInput from './inputs/FillBlankInput.vue'
import MatchingInput from './inputs/MatchingInput.vue'
import OrderingInput from './inputs/OrderingInput.vue'
import TrueFalseInput from './inputs/TrueFalseInput.vue'
import TypedInput from './inputs/TypedInput.vue'
import Icon from './ui/Icon.vue'
import ProgressBar from './ui/ProgressBar.vue'
import PupilButton from './ui/PupilButton.vue'

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
  const title = answer.correct
    ? 'Correct!'
    : answer.response
      ? 'Not quite'
      : "Here's the answer" // the learner said they didn't know
  return {
    correct: answer.correct,
    title,
    answer: answerText(q),
    explanation: q.explanation,
  }
})
/** How each part of the checked answer did, for the input to show. */
const marks = computed(() => {
  const q = question.value
  const answer = q && answers.value[q.id]
  return feedback.value && q && answer ? feedbackFor(q, answer.response) : null
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

/** Placement offers "I don't know", counted as wrong, so the learner doesn't guess their way
 * too far ahead. */
function dontKnow() {
  const q = question.value
  if (!q || feedback.value) return
  answers.value[q.id] = { response: null, correct: false }
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
        given: answer.response && responseText(q, answer.response),
        answer: answerText(q),
      }
    })
})

const footerStyle = computed(() => {
  if (!feedback.value) return 'border-ink-200'
  return feedback.value.correct ? 'border-leaf-200 bg-leaf-50' : 'border-coral-200 bg-coral-50'
})
</script>

<template>
  <div class="fixed inset-0 z-10 flex flex-col bg-white" @keydown.enter.prevent="onEnter">
    <header class="mx-auto flex w-full max-w-md items-center gap-3 px-4 py-4">
      <button
        class="flex size-11 items-center justify-center rounded-xl text-ink-400 hover:bg-ink-100 hover:text-ink-700"
        aria-label="Quit the lesson"
        @click="emit('close')"
      >
        <Icon name="close" />
      </button>
      <ProgressBar :percent="progress" />
    </header>

    <main class="mx-auto flex w-full max-w-md flex-1 flex-col gap-5 overflow-y-auto px-4 py-6">
      <p v-if="!lesson && error" class="text-coral-600">{{ error }}</p>
      <p v-else-if="!lesson" class="text-ink-500">Loading…</p>

      <!-- A placement lesson that has already been taken -->
      <template v-else-if="taken">
        <h2 class="text-2xl font-extrabold">{{ lesson.title }}</h2>
        <p class="text-lg">
          You've already taken this placement and got
          <strong>{{ attempts[0].correct }} of {{ attempts[0].total }}</strong> right.
        </p>
      </template>

      <!-- Results, once the lesson is finished -->
      <template v-else-if="finished">
        <h2 class="text-2xl font-extrabold">
          {{ lesson.purpose === 'placement' ? 'Placement done!' : 'Lesson complete!' }}
        </h2>
        <p class="text-lg">
          You got
          <strong>{{ results.filter((r) => r.correct).length }} of {{ results.length }}</strong>
          right<span v-if="saved && saved.number > 1"> on attempt {{ saved.number }}</span>.
        </p>
        <ol class="flex flex-col gap-2">
          <li
            v-for="r in results"
            :key="r.id"
            class="rounded-xl border-2 border-ink-100 px-4 py-3"
          >
            <p class="font-medium">
              <span :class="r.correct ? 'text-leaf-600' : 'text-coral-600'">
                {{ r.correct ? '✓' : '✗' }}
              </span>
              <span class="markdown-inline" v-html="renderInline(r.prompt)" />
            </p>
            <p v-if="!r.correct" class="text-sm text-ink-600">
              <template v-if="r.given">You said {{ r.given }}; </template>
              <template v-else>You didn't know; </template>
              the answer is {{ r.answer }}.
            </p>
          </li>
        </ol>
      </template>

      <!-- A teach card -->
      <template v-else-if="item && item.kind === 'teach_card'">
        <p class="text-sm font-semibold tracking-wide text-lake-600 uppercase">New idea</p>
        <h2 class="text-2xl font-extrabold">{{ item.title }}</h2>
        <div class="markdown text-lg" v-html="renderMarkdown(item.text)" />
      </template>

      <!-- A question -->
      <template v-else-if="question">
        <div class="markdown text-xl" v-html="renderMarkdown(question.prompt)" />

        <!-- Keyed by run and question, so each starts empty, and is shuffled afresh -->
        <ChoiceInput
          v-if="question.kind === 'multiple_choice'"
          :key="`${run}-${question.id}`"
          v-model="response"
          :question="question"
          :disabled="!!feedback"
          :marks="marks"
        />
        <TrueFalseInput
          v-else-if="question.kind === 'true_false'"
          :key="`${run}-${question.id}`"
          v-model="response"
          :disabled="!!feedback"
          :marks="marks"
        />
        <FillBlankInput
          v-else-if="question.kind === 'fill_blank'"
          :key="`${run}-${question.id}`"
          v-model="response"
          :question="question"
          :disabled="!!feedback"
          :marks="marks"
        />
        <OrderingInput
          v-else-if="question.kind === 'ordering'"
          :key="`${run}-${question.id}`"
          v-model="response"
          :question="question"
          :disabled="!!feedback"
          :marks="marks"
        />
        <MatchingInput
          v-else-if="question.kind === 'matching'"
          :key="`${run}-${question.id}`"
          v-model="response"
          :question="question"
          :disabled="!!feedback"
          :marks="marks"
        />
        <TypedInput
          v-else
          :key="`${run}-${question.id}`"
          v-model="response"
          :question="question"
          :disabled="!!feedback"
          :marks="marks"
        />
      </template>
    </main>

    <footer
      v-if="lesson && !taken"
      :class="['safe-bottom border-t-2 px-4 pt-5', footerStyle]"
    >
      <div class="mx-auto flex max-w-md flex-col gap-3">
        <div v-if="feedback">
          <p :class="['text-xl font-extrabold', feedback.correct ? 'text-leaf-700' : 'text-coral-700']">
            {{ feedback.title }}
          </p>
          <p v-if="!feedback.correct" class="font-medium">Answer: {{ feedback.answer }}</p>
          <div class="markdown text-ink-700" v-html="renderMarkdown(feedback.explanation)" />
        </div>
        <template v-if="finished">
          <p v-if="busy" class="text-ink-500">Saving…</p>
          <p v-else-if="saveProblem" class="text-coral-600">{{ saveProblem.message }}</p>
          <div class="flex flex-col gap-3">
            <!-- Not while saving: the topic would still show this lesson as the next one -->
            <PupilButton block :disabled="busy" @click="emit('close')">Continue</PupilButton>
            <PupilButton
              v-if="saveProblem?.canRetry"
              variant="secondary"
              block
              :disabled="busy"
              @click="save"
            >
              Try saving again
            </PupilButton>
            <PupilButton
              v-if="lesson.purpose === 'lesson'"
              variant="secondary"
              block
              :disabled="busy"
              @click="load"
            >
              Retry lesson
            </PupilButton>
          </div>
        </template>
        <div v-else-if="question && !feedback" class="flex gap-3">
          <PupilButton
            v-if="lesson.purpose === 'placement'"
            variant="secondary"
            class="flex-1"
            @click="dontKnow"
          >
            I don't know
          </PupilButton>
          <PupilButton :disabled="!response" class="flex-1" @click="check">Check</PupilButton>
        </div>
        <PupilButton
          v-else
          block
          :variant="feedback && !feedback.correct ? 'danger' : 'primary'"
          @click="next"
        >
          {{ isLast ? 'Finish' : 'Continue' }}
        </PupilButton>
      </div>
    </footer>
  </div>
</template>
