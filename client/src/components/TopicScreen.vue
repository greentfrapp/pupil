<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  extendTopic,
  getTopic,
  prepareTopic,
  type Job,
  type LessonSummary,
  type Topic,
} from '../api/topics'
import { nextUp, screen } from '../topicState'

const props = defineProps<{ topicId: string }>()
const emit = defineEmits<{ play: [lessonId: string]; close: [] }>()

const topic = ref<Topic | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)

// While the agent prepares something, check back until it's done.
const POLL_MS = 2000
let timer: ReturnType<typeof setTimeout> | undefined

async function load() {
  clearTimeout(timer)
  try {
    show(await getTopic(props.topicId))
    error.value = null
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    timer = setTimeout(load, POLL_MS)
  }
}

function show(t: Topic) {
  topic.value = t
  clearTimeout(timer)
  if (t.last_run?.state === 'running') timer = setTimeout(load, POLL_MS)
}

/** Ask for a run: the one the topic needs, after a failure, or one to go further. */
async function ask(request: (id: string) => Promise<Topic>) {
  if (busy.value) return
  busy.value = true
  try {
    show(await request(props.topicId))
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

onMounted(load)
onUnmounted(() => clearTimeout(timer))

const current = computed(() => topic.value && screen(topic.value))
const next = computed(() => topic.value && nextUp(topic.value))
const lessons = computed(
  () => new Map((topic.value?.lessons ?? []).map((l) => [l.lesson_id, l])),
)
const placement = computed(() =>
  topic.value?.lessons.find((l) => l.purpose === 'placement' && l.attempts > 0),
)
const nextLesson = computed(() =>
  next.value?.kind === 'ready' ? lessons.value.get(next.value.lessonId) : undefined,
)
/** Lessons from the plan the learner has taken, for the finished screen. */
const taken = computed(() =>
  (topic.value?.lessons ?? []).filter((l) => l.purpose === 'lesson' && l.attempts > 0),
)
const takenCorrect = computed(() => taken.value.reduce((n, l) => n + (l.latest_correct ?? 0), 0))
const takenQuestions = computed(() => taken.value.reduce((n, l) => n + l.questions, 0))

const WAITING: Record<Job, string> = {
  placement: 'Writing a few questions to see what you know…',
  plan: 'Building your plan…',
  next_lesson: 'Writing your next lesson…',
  extend: 'Adding more to your plan…',
}

function score(l: LessonSummary): string {
  return `${l.latest_correct} of ${l.questions}`
}

const buttonClass =
  'rounded-xl bg-blue-600 px-6 py-3 text-lg font-semibold text-white hover:bg-blue-700 disabled:opacity-40'
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <header class="flex items-center gap-4 px-4 py-4">
      <button
        class="text-2xl text-gray-400 hover:text-gray-700"
        aria-label="All topics"
        @click="emit('close')"
      >
        ←
      </button>
      <h1 class="truncate text-xl font-bold">{{ topic?.request }}</h1>
    </header>

    <main class="mx-auto flex w-full max-w-xl flex-1 flex-col gap-5 px-4 py-6">
      <p v-if="!topic && error" class="text-red-600">{{ error }}</p>
      <p v-else-if="!topic" class="text-gray-500">Loading…</p>

      <!-- Before the plan: placement, or waiting for the plan -->
      <template v-else-if="current === 'start'">
        <template v-if="next?.kind === 'ready'">
          <h2 class="text-2xl font-bold">Let's see what you already know</h2>
          <p class="text-lg text-gray-700">
            A few questions, from easy to hard. When you don't know one, tap
            <strong>I don't know</strong> rather than guessing, so your plan starts in the right
            place.
          </p>
        </template>
        <template v-else-if="placement">
          <h2 class="text-2xl font-bold">Thanks!</h2>
          <p class="text-lg text-gray-700">
            You got {{ score(placement) }} right. Your plan is built from that.
          </p>
        </template>
        <template v-else-if="topic.profile.level === 'new'">
          <h2 class="text-2xl font-bold">Starting from the beginning</h2>
          <p class="text-lg text-gray-700">Your plan is built from your answers.</p>
        </template>
      </template>

      <!-- The plan, shown back until the first lesson is taken -->
      <template v-else-if="current === 'plan' && topic.syllabus">
        <p class="text-sm font-semibold tracking-wide text-blue-600 uppercase">Your plan</p>
        <h2 class="text-2xl font-bold">{{ topic.syllabus.goal }}</h2>
        <p v-if="topic.syllabus.rationale" class="text-lg text-gray-700">
          {{ topic.syllabus.rationale }}
        </p>
        <ol class="flex flex-col gap-2">
          <li
            v-for="(unit, i) in topic.path"
            :key="unit.unit_id"
            class="flex gap-3 rounded-xl border-2 border-gray-100 px-4 py-3"
          >
            <span class="font-bold text-gray-400">{{ i + 1 }}</span>
            <span class="flex flex-col">
              <span class="font-semibold">{{ unit.title }}</span>
              <span class="text-gray-600">{{ unit.summary }}</span>
              <span class="text-sm text-gray-400">
                {{ unit.stops }} {{ unit.stops === 1 ? 'lesson' : 'lessons' }}
              </span>
            </span>
          </li>
        </ol>
      </template>

      <!-- The path, under a celebration once it's finished -->
      <template v-else-if="topic.syllabus">
        <div
          v-if="current === 'finished'"
          class="flex flex-col gap-3 rounded-xl border-2 border-green-200 bg-green-50 p-5"
        >
          <h2 class="text-2xl font-bold">You've finished {{ topic.request }}!</h2>
          <p class="text-lg">
            {{ taken.length }} {{ taken.length === 1 ? 'lesson' : 'lessons' }}, and
            <strong>{{ takenCorrect }} of {{ takenQuestions }}</strong> questions right.
          </p>
          <template v-if="next?.kind === 'done'">
            <p class="text-gray-700">
              Want to keep going? Pupil can add units that go deeper, picking up from here.
            </p>
            <button
              :disabled="busy"
              :class="[buttonClass, 'self-start']"
              @click="ask(extendTopic)"
            >
              Go further
            </button>
          </template>
        </div>
        <div>
          <h2 class="text-2xl font-bold">{{ topic.syllabus.goal }}</h2>
          <p v-if="topic.syllabus.rationale" class="text-gray-600">
            {{ topic.syllabus.rationale }}
          </p>
        </div>
        <ol class="flex flex-col gap-3">
          <li
            v-for="unit in topic.path"
            :key="unit.unit_id"
            :class="[
              'rounded-xl border-2 px-4 py-3',
              unit.lesson_ids.length ? 'border-gray-200' : 'border-dashed border-gray-200',
            ]"
          >
            <p :class="['font-semibold', unit.lesson_ids.length ? '' : 'text-gray-400']">
              {{ unit.title }}
            </p>
            <p :class="['text-sm', unit.lesson_ids.length ? 'text-gray-600' : 'text-gray-400']">
              {{ unit.summary }}
            </p>
            <div class="mt-3 flex flex-wrap gap-2">
              <template v-for="id in unit.lesson_ids" :key="id">
                <button
                  v-if="lessons.get(id)"
                  :class="[
                    'rounded-full border-2 px-4 py-1.5 text-left',
                    id === topic.next_lesson_id
                      ? 'border-blue-500 bg-blue-50 font-semibold'
                      : 'border-green-200 bg-green-50',
                  ]"
                  :title="id === topic.next_lesson_id ? 'Start' : 'Take it again'"
                  @click="emit('play', id)"
                >
                  <span v-if="lessons.get(id)!.attempts" class="text-green-600">✓</span>
                  {{ lessons.get(id)!.title }}
                  <span v-if="lessons.get(id)!.attempts" class="text-sm text-gray-500">
                    {{ score(lessons.get(id)!) }}
                  </span>
                </button>
              </template>
              <!-- Stops whose lessons aren't written yet -->
              <span
                v-for="k in unit.stops - unit.lesson_ids.length"
                :key="`stop-${k}`"
                class="rounded-full border-2 border-dashed border-gray-200 px-4 py-1.5 text-gray-400"
              >
                Lesson {{ unit.lesson_ids.length + k }}
              </span>
            </div>
          </li>
        </ol>
      </template>
    </main>

    <!-- What's next: start it, wait for it, or ask for it again -->
    <footer
      v-if="topic && next && next.kind !== 'done'"
      class="sticky bottom-0 border-t-2 border-gray-100 bg-white px-4 py-5"
    >
      <div class="mx-auto flex max-w-xl items-center justify-end gap-3">
        <template v-if="next.kind === 'ready'">
          <p v-if="current === 'path' && nextLesson" class="flex-1 truncate font-medium">
            Next: {{ nextLesson.title }}
          </p>
          <button :class="buttonClass" @click="emit('play', next.lessonId)">
            {{ current === 'plan' ? 'Start your first lesson' : 'Start' }}
          </button>
        </template>
        <p v-else-if="next.kind === 'waiting'" class="flex-1 animate-pulse text-gray-600">
          {{ WAITING[next.job] }}
        </p>
        <template v-else>
          <p class="flex-1 text-red-600">
            Something went wrong preparing this<span v-if="next.error">: {{ next.error }}</span>
          </p>
          <button :disabled="busy" :class="buttonClass" @click="ask(prepareTopic)">
            Try again
          </button>
        </template>
      </div>
    </footer>
  </div>
</template>
