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

onMounted(load)
onUnmounted(() => clearTimeout(timer))

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
/** Each node's place on the whole path, for the wave. */
const order = computed(() => new Map(nodes.value.map((n, i) => [n.key, i])))

/** The node whose card is open. */
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

// A gentle wave, left and right, along the path.
const WAVE = [0, 1, 1.5, 1, 0, -1, -1.5, -1]
function sway(i: number): string {
  return `translateX(${WAVE[i % WAVE.length] * 3}rem)`
}

// Units take turns at the palette. Whole class names, so Tailwind finds them.
const UNIT_LOOKS = [
  'bg-leaf-500 text-white shadow-[0_4px_0_var(--color-leaf-700)]',
  'bg-lake-500 text-white shadow-[0_4px_0_var(--color-lake-700)]',
  'bg-coral-500 text-white shadow-[0_4px_0_var(--color-coral-700)]',
  'bg-sun-400 text-sun-900 shadow-[0_4px_0_var(--color-sun-600)]',
]

function nodeLook(n: PathNode): string {
  if (n.state === 'locked') return 'bg-ink-200 text-ink-400 [--edge:var(--color-ink-300)]'
  if (n.state === 'done' && n.correct === n.questions)
    return 'bg-sun-400 text-white [--edge:var(--color-sun-600)]'
  if (n.state === 'done') return 'bg-leaf-500 text-white [--edge:var(--color-leaf-700)]'
  if (n.state === 'current') return 'bg-leaf-500 text-white [--edge:var(--color-leaf-700)]'
  return 'bg-lake-400 text-white [--edge:var(--color-lake-600)]'
}

function nodeLabel(n: PathNode): string {
  if (n.state === 'locked') return 'A lesson still to come'
  if (n.state === 'done') return `${n.title}, done: ${n.correct} of ${n.questions}`
  return n.title ?? ''
}
</script>

<template>
  <div class="flex min-h-dvh flex-col" @click="selected = null">
    <header
      class="sticky top-0 z-20 border-b-2 border-ink-200 bg-ink-50/95 px-4 py-3 backdrop-blur"
    >
      <div class="mx-auto flex max-w-md items-center gap-3">
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
                'flex size-10 shrink-0 items-center justify-center rounded-xl text-lg font-black',
                UNIT_LOOKS[i % UNIT_LOOKS.length],
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
          <div
            class="flex size-14 items-center justify-center rounded-full bg-sun-400 text-white shadow-[0_4px_0_var(--color-sun-600)]"
          >
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
            <PupilButton :disabled="busy" class="self-start" @click="ask(extendTopic)">
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

        <section v-for="(section, u) in sections" :key="section.unitId" class="flex flex-col">
          <!-- The unit's banner -->
          <div
            :class="[
              'flex items-center justify-between gap-3 rounded-2xl px-5 py-4',
              UNIT_LOOKS[u % UNIT_LOOKS.length],
            ]"
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

          <!-- Its lessons, winding down the page -->
          <ol class="flex flex-col items-center gap-7 py-10">
            <li
              v-for="node in section.nodes"
              :id="`node-${node.key}`"
              :key="node.key"
              class="relative flex flex-col items-center"
            >
              <!-- The node sways along the wave; its card stays centred below -->
              <div class="relative" :style="{ transform: sway(order.get(node.key)!) }">
                <!-- Where the learner is up to -->
                <span
                  v-if="node.key === hereKey && selected !== node.key"
                  :class="[
                    'bob absolute -top-12 left-1/2 z-10 rounded-xl border-2 px-3 py-1.5 text-sm font-extrabold whitespace-nowrap',
                    next?.kind === 'stuck'
                      ? 'border-coral-200 bg-coral-50 text-coral-600'
                      : 'border-ink-200 bg-white text-leaf-600',
                    next?.kind === 'waiting' && 'animate-pulse',
                  ]"
                >
                  <template v-if="next?.kind === 'ready'">START</template>
                  <template v-else-if="next?.kind === 'waiting'">{{ WAITING[next.job] }}</template>
                  <template v-else-if="next?.kind === 'stuck'">Something went wrong</template>
                </span>
                <span
                  v-if="node.state === 'current'"
                  class="absolute -inset-2 animate-ping rounded-full border-4 border-leaf-300 [animation-duration:2s]"
                  aria-hidden="true"
                />
                <button
                  :class="[
                    'relative flex items-center justify-center rounded-full shadow-[0_6px_0_var(--edge)] transition-[transform,box-shadow] duration-75 active:translate-y-1.5 active:shadow-none',
                    node.state === 'current' ? 'size-20' : 'size-17',
                    nodeLook(node),
                  ]"
                  :aria-label="nodeLabel(node)"
                  :aria-expanded="selected === node.key"
                  @click.stop="toggle(node.key)"
                >
                  <Icon
                    :name="
                      node.state === 'locked' ? 'lock' : node.state === 'done' ? 'check' : 'star'
                    "
                    :size="node.state === 'current' ? 36 : 30"
                  />
                </button>
              </div>

              <!-- The node's card -->
              <div
                v-if="selected === node.key"
                class="absolute top-full z-20 mt-4 flex w-72 flex-col gap-3 rounded-2xl border-2 border-ink-200 bg-white p-4 shadow-lg"
                @click.stop
              >
                <template v-if="node.lessonId">
                  <p class="text-lg font-extrabold">{{ node.title }}</p>
                  <p v-if="node.state === 'done'" class="text-ink-600">
                    Your score: {{ node.correct }} of {{ node.questions }}
                  </p>
                  <p v-else-if="node.state === 'ready'" class="text-ink-600">
                    Written and ready for you.
                  </p>
                  <PupilButton
                    block
                    :variant="node.state === 'done' ? 'secondary' : 'primary'"
                    @click="emit('play', node.lessonId)"
                  >
                    {{ node.state === 'done' ? 'Review' : 'Start' }}
                  </PupilButton>
                </template>
                <template v-else-if="node.here && next?.kind === 'waiting'">
                  <p class="font-extrabold">Being written…</p>
                  <p class="text-ink-600">{{ WAITING[next.job] }}</p>
                </template>
                <template v-else-if="node.here && next?.kind === 'stuck'">
                  <p class="font-extrabold text-coral-600">Something went wrong</p>
                  <p v-if="next.error" class="text-ink-600">{{ next.error }}</p>
                  <PupilButton block :disabled="busy" @click="ask(prepareTopic)">
                    Try again
                  </PupilButton>
                </template>
                <template v-else>
                  <p class="font-extrabold">Still to come</p>
                  <p class="text-ink-600">Pupil writes it once you reach it.</p>
                </template>
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
              'flex size-20 items-center justify-center rounded-full shadow-[0_6px_0_var(--edge)] transition-[transform,box-shadow] duration-75 active:translate-y-1.5 active:shadow-none',
              topic.finished
                ? 'bg-sun-400 text-white [--edge:var(--color-sun-600)]'
                : 'bg-ink-200 text-ink-400 [--edge:var(--color-ink-300)]',
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
              <PupilButton block :disabled="busy" @click="ask(extendTopic)">Go further</PupilButton>
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
          <PupilButton block @click="emit('play', next.lessonId)">
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
          <PupilButton block :disabled="busy" @click="ask(prepareTopic)">Try again</PupilButton>
        </template>
      </div>
    </footer>
  </div>
</template>
