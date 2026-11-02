<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import {
  extendTopic,
  getTopic,
  prepareTopic,
  type Job,
  type LessonSummary,
  type Topic,
} from '../api/topics'
import { nextUp, pathSections, screen, type PathNode } from '../topicState'
import Icon from './ui/Icon.vue'
import PupilButton from './ui/PupilButton.vue'

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
  if (screen(t) === 'path') scrollToHere()
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

/** Whether the page has scrolled, so the header casts a shadow over what's under it. */
const pastTop = ref(false)
function onScroll() {
  pastTop.value = window.scrollY > 0
}

onMounted(() => {
  load()
  window.addEventListener('scroll', onScroll, { passive: true })
})
onUnmounted(() => {
  clearTimeout(timer)
  window.removeEventListener('scroll', onScroll)
})

const current = computed(() => topic.value && screen(topic.value))
const next = computed(() => topic.value && nextUp(topic.value))
const placement = computed(() =>
  topic.value?.lessons.find((l) => l.purpose === 'placement' && l.attempts > 0),
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

const sections = computed(() => (topic.value ? pathSections(topic.value) : []))
const nodes = computed(() => sections.value.flatMap((s) => s.nodes))
const stopsDone = computed(() => nodes.value.filter((n) => n.state === 'done').length)
/** Where the learner is up to; the trophy once there's nowhere else. */
const hereKey = computed(() => nodes.value.find((n) => n.here)?.key ?? 'trophy')

/** The trophy's card, when it's open. */
const selected = ref<string | null>(null)
function toggle(key: string) {
  selected.value = selected.value === key ? null : key
}

// Bring the learner's place into view when the path first shows.
let scrolled = false
async function scrollToHere() {
  if (scrolled || !nodes.value.length) return
  scrolled = true
  await nextTick()
  document.getElementById(`node-${hereKey.value}`)?.scrollIntoView({ block: 'center' })
}

// Units take turns at their own palette. Each sets --unit (the banner, a done lesson's border and
// score, and the START button) and --unit-dark (a done lesson's title, and hovering) for what's
// inside it. Whole class names, so Tailwind finds them.
const UNIT_LOOKS = [
  '[--unit:var(--color-moss-500)] [--unit-dark:var(--color-moss-600)]',
  '[--unit:var(--color-ember-500)] [--unit-dark:var(--color-ember-600)]',
  '[--unit:var(--color-pine-500)] [--unit-dark:var(--color-pine-600)]',
  '[--unit:var(--color-plum-500)] [--unit-dark:var(--color-plum-600)]',
]

function unitLook(u: number): string {
  return UNIT_LOOKS[u % UNIT_LOOKS.length]
}

function doneLabel(n: PathNode): string {
  const perfect = n.correct === n.questions ? ', a perfect score' : ''
  return `${n.title}, ${n.correct} of ${n.questions} right${perfect}. Retry it`
}
</script>

<template>
  <div class="flex min-h-dvh flex-col" @click="selected = null">
    <header
      :class="[
        'sticky top-0 z-20 bg-ink-50 transition-shadow duration-200',
        pastTop && 'shadow-[0_2px_8px_rgb(0_0_0/0.08)]',
      ]"
    >
      <div class="mx-auto flex w-full max-w-md items-center gap-3 px-4 py-4">
        <button
          class="flex size-11 shrink-0 items-center justify-center rounded-xl text-ink-400 hover:bg-ink-100 hover:text-ink-700"
          aria-label="All topics"
          @click="emit('close')"
        >
          <Icon name="back" />
        </button>
        <h1 class="min-w-0 flex-1 truncate text-xl font-extrabold">{{ topic?.request }}</h1>
        <span
          v-if="nodes.length && (current === 'path' || current === 'finished')"
          class="flex shrink-0 items-center gap-1 rounded-full bg-white px-3 py-1 text-sm font-extrabold text-leaf-600 ring-2 ring-ink-200"
          :aria-label="`${stopsDone} of ${nodes.length} lessons done`"
        >
          <Icon name="check" :size="16" />
          {{ stopsDone }}/{{ nodes.length }}
        </span>
      </div>
    </header>

    <main class="mx-auto flex w-full max-w-md flex-1 flex-col gap-5 px-4 py-6">
      <p v-if="!topic && error" class="text-coral-600">{{ error }}</p>
      <p v-else-if="!topic" class="text-ink-500">Loading…</p>

      <!-- Before the plan: placement, or waiting for the plan -->
      <template v-else-if="current === 'start'">
        <template v-if="next?.kind === 'ready'">
          <h2 class="text-2xl font-extrabold">Let's see what you already know</h2>
          <p class="text-lg text-ink-700">
            A few questions, from easy to hard. When you don't know one, tap
            <strong>I don't know</strong> rather than guessing, so your plan starts in the right
            place.
          </p>
        </template>
        <template v-else-if="placement">
          <h2 class="text-2xl font-extrabold">Thanks!</h2>
          <p class="text-lg text-ink-700">
            You got {{ score(placement) }} right. Your plan is built from that.
          </p>
        </template>
        <template v-else-if="topic.profile.level === 'new'">
          <h2 class="text-2xl font-extrabold">Starting from the beginning</h2>
          <p class="text-lg text-ink-700">Your plan is built from your answers.</p>
        </template>
      </template>

      <!-- The plan, shown back until the first lesson is taken -->
      <template v-else-if="current === 'plan' && topic.syllabus">
        <p class="text-sm font-semibold tracking-wide text-lake-600 uppercase">Your plan</p>
        <h2 class="text-2xl font-extrabold">{{ topic.syllabus.goal }}</h2>
        <p v-if="topic.syllabus.rationale" class="text-lg text-ink-700">
          {{ topic.syllabus.rationale }}
        </p>
        <ol class="flex flex-col gap-3">
          <li
            v-for="(unit, i) in topic.path"
            :key="unit.unit_id"
            class="flex gap-4 rounded-2xl border-2 border-ink-200 bg-white p-4"
          >
            <span
              :class="[
                'flex size-10 shrink-0 items-center justify-center rounded-xl bg-(--unit) text-lg font-black text-white',
                unitLook(i),
              ]"
            >
              {{ i + 1 }}
            </span>
            <span class="flex flex-col">
              <span class="font-extrabold">{{ unit.title }}</span>
              <span class="text-ink-600">{{ unit.summary }}</span>
              <span class="text-sm text-ink-400">
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
          class="flex flex-col gap-3 rounded-2xl border-2 border-sun-200 bg-sun-50 p-5"
        >
          <div class="flex size-14 items-center justify-center rounded-full bg-sun-400 text-white">
            <Icon name="trophy" :size="30" />
          </div>
          <h2 class="text-2xl font-extrabold">You've finished {{ topic.request }}!</h2>
          <p class="text-lg">
            {{ taken.length }} {{ taken.length === 1 ? 'lesson' : 'lessons' }}, and
            <strong>{{ takenCorrect }} of {{ takenQuestions }}</strong> questions right.
          </p>
          <template v-if="next?.kind === 'done'">
            <p class="text-ink-700">
              Want to keep going? Pupil can add units that go deeper, picking up from here.
            </p>
            <PupilButton
              variant="success"
              :disabled="busy"
              class="self-start"
              @click="ask(extendTopic)"
            >
              Go further
            </PupilButton>
          </template>
        </div>
        <p
          v-if="placement"
          class="flex items-center gap-2 self-center rounded-full bg-white px-4 py-1.5 text-sm text-ink-600 ring-2 ring-ink-200"
        >
          <Icon name="star" :size="16" class="text-sun-500" />
          Placement: {{ score(placement) }}
        </p>

        <section
          v-for="(section, u) in sections"
          :key="section.unitId"
          :class="['flex flex-col', unitLook(u)]"
        >
          <!-- The unit's banner -->
          <div
            class="flex items-center justify-between gap-3 rounded-2xl bg-(--unit) px-5 py-4 text-white"
          >
            <div class="min-w-0">
              <p class="text-sm font-extrabold tracking-wide uppercase opacity-80">
                Unit {{ u + 1 }}
              </p>
              <h2 class="text-xl font-extrabold">{{ section.title }}</h2>
              <p class="opacity-90">{{ section.summary }}</p>
            </div>
            <span class="shrink-0 text-sm font-extrabold opacity-90">
              {{ section.done }}/{{ section.nodes.length }}
            </span>
          </div>

          <!-- Its lessons, as cards -->
          <ol class="flex flex-col gap-3 py-5">
            <li v-for="node in section.nodes" :id="`node-${node.key}`" :key="node.key">
              <!-- Done: a card in the unit's colour, with the score; tap it to retry -->
              <button
                v-if="node.state === 'done' && node.lessonId"
                :class="[
                  'flex flex-col w-full items-center justify-between gap-3 rounded-2xl border-2 border-(--unit) bg-white px-4 py-4 text-left text-(--unit-dark) hover:bg-ink-50',
                ]"
                :aria-label="doneLabel(node)"
                @click="emit('play', node.lessonId)"
              >
                <span class="flex w-full min-w-0">
                  <span class="text-lg font-extrabold">{{ node.title }}</span>
                </span>
                <span class="flex justify-between w-full">
                  <span class="flex items-center gap-1 text-sm text-(--unit)">
                    {{ node.correct }} of {{ node.questions }} right
                    <Icon
                      v-if="node.correct === node.questions"
                      name="star"
                      :size="16"
                      class="text-sun-500 ml-1"
                    />
                  </span>
                  <span
                    class="flex shrink-0 items-center gap-1 text-sm font-extrabold tracking-wide uppercase"
                  >
                    <Icon name="retry" :size="16" weight="bold" />
                  </span>
                </span>
              </button>

              <!-- Up next: START in the unit's colour -->
              <div
                v-else-if="node.state === 'current' && node.lessonId"
                class="flex flex-col gap-3 rounded-2xl border-2 border-ink-200 bg-white p-4"
              >
                <p class="text-lg font-extrabold">{{ node.title }}</p>
                <PupilButton variant="unit" block @click="emit('play', node.lessonId!)">
                  Start
                </PupilButton>
              </div>

              <!-- Written ahead, not next: tap it to take it early -->
              <button
                v-else-if="node.lessonId"
                class="flex w-full items-center justify-between gap-3 rounded-2xl border-2 border-ink-200 bg-white px-4 py-4 text-left hover:bg-ink-50"
                @click="emit('play', node.lessonId)"
              >
                <span class="min-w-0 text-lg font-extrabold">{{ node.title }}</span>
                <span class="shrink-0 text-sm text-ink-400">Ready</span>
              </button>

              <!-- Not written yet: being written, stuck, or still to come -->
              <div
                v-else
                class="flex flex-col gap-3 rounded-2xl border-2 border-ink-200 bg-ink-100 px-4 py-4 text-ink-500"
              >
                <p
                  v-if="node.here && next?.kind === 'waiting'"
                  class="animate-pulse font-extrabold"
                >
                  {{ WAITING[next.job] }}
                </p>
                <template v-else-if="node.here && next?.kind === 'stuck'">
                  <p class="font-extrabold text-coral-600">
                    Something went wrong<span v-if="next.error">: {{ next.error }}</span>
                  </p>
                  <PupilButton variant="unit" block :disabled="busy" @click="ask(prepareTopic)">
                    Try again
                  </PupilButton>
                </template>
                <p v-else class="flex items-center gap-2 font-extrabold">
                  <Icon name="lock" :size="18" />
                  Still to come
                </p>
              </div>
            </li>
          </ol>
        </section>

        <!-- The end of the path -->
        <div id="node-trophy" class="relative flex flex-col items-center pb-10">
          <span
            v-if="hereKey === 'trophy' && next?.kind === 'waiting'"
            class="bob absolute -top-12 left-1/2 animate-pulse rounded-xl border-2 border-ink-200 bg-white px-3 py-1.5 text-sm font-extrabold whitespace-nowrap text-leaf-600"
          >
            {{ WAITING[next.job] }}
          </span>
          <button
            :class="[
              'flex size-20 items-center justify-center rounded-full',
              topic.finished ? 'bg-sun-400 text-white' : 'bg-ink-200 text-ink-400',
            ]"
            :aria-label="topic.finished ? 'Finished! Go further' : 'The end of the path'"
            :aria-expanded="selected === 'trophy'"
            @click.stop="toggle('trophy')"
          >
            <Icon name="trophy" :size="38" />
          </button>
          <div
            v-if="selected === 'trophy'"
            class="mt-4 flex w-72 flex-col gap-3 rounded-2xl border-2 border-ink-200 bg-white p-4 shadow-lg"
            @click.stop
          >
            <template v-if="next?.kind === 'done'">
              <p class="text-lg font-extrabold">Want to keep going?</p>
              <p class="text-ink-600">Pupil can add units that go deeper, picking up from here.</p>
              <PupilButton variant="success" block :disabled="busy" @click="ask(extendTopic)">
                Go further
              </PupilButton>
            </template>
            <template v-else-if="next?.kind === 'waiting' && hereKey === 'trophy'">
              <p class="font-extrabold">{{ WAITING[next.job] }}</p>
            </template>
            <template v-else>
              <p class="font-extrabold">The finish line</p>
              <p class="text-ink-600">Take every lesson on the path to reach it.</p>
            </template>
          </div>
        </div>
      </template>
    </main>

    <!-- Before the path, what's next: start it, wait for it, or ask for it again. On the path,
         its place does this. -->
    <footer
      v-if="topic && next && next.kind !== 'done' && (current === 'start' || current === 'plan')"
      class="safe-bottom sticky bottom-0 border-t-2 border-ink-200 bg-ink-50 px-4 pt-5"
    >
      <div class="mx-auto flex max-w-md flex-col gap-3">
        <template v-if="next.kind === 'ready'">
          <PupilButton variant="success" block @click="emit('play', next.lessonId)">
            {{ current === 'plan' ? 'Start your first lesson' : 'Start' }}
          </PupilButton>
        </template>
        <p v-else-if="next.kind === 'waiting'" class="animate-pulse py-3 text-center text-ink-600">
          {{ WAITING[next.job] }}
        </p>
        <template v-else>
          <p class="text-coral-600">
            Something went wrong preparing this<span v-if="next.error">: {{ next.error }}</span>
          </p>
          <PupilButton variant="success" block :disabled="busy" @click="ask(prepareTopic)">
            Try again
          </PupilButton>
        </template>
      </div>
    </footer>
  </div>
</template>
