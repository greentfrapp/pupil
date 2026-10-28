<script setup lang="ts">
import { computed, ref } from 'vue'
import { createTopic, type Depth, type Level, type Why } from '../api/topics'
import { DEPTH, LEVEL, WHY } from '../setup'
import { choiceClass, inputClass } from './inputs/styles'
import Icon from './ui/Icon.vue'
import ProgressBar from './ui/ProgressBar.vue'
import PupilButton from './ui/PupilButton.vue'

const emit = defineEmits<{ created: [topicId: string]; close: [] }>()

// What the learner wants to learn, then the setup questions, one per screen.
const steps = ['request', 'why', 'depth', 'level', 'specific'] as const
const step = ref(0)
const current = computed(() => steps[step.value])
const questions = { why: WHY, depth: DEPTH, level: LEVEL }
/** The setup question on screen, on the steps that are one. */
const question = computed(() => questions[current.value as keyof typeof questions])

const request = ref('')
const why = ref<Why | null>(null)
const depth = ref<Depth | null>(null)
const level = ref<Level | null>(null)
const specific = ref('')
const answers = { why, depth, level }

const busy = ref(false)
const error = ref<string | null>(null)

function back() {
  if (step.value === 0) emit('close')
  else step.value--
}

function pick(value: string) {
  answers[question.value.key].value = value as never
  step.value++
}

async function start() {
  if (busy.value || !why.value || !depth.value || !level.value) return
  busy.value = true
  error.value = null
  try {
    const profile = {
      why: why.value,
      depth: depth.value,
      level: level.value,
      specific: specific.value.trim() || null,
    }
    const topic = await createTopic(request.value.trim(), profile)
    emit('created', topic.id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-10 flex flex-col bg-white">
    <header class="mx-auto flex w-full max-w-md items-center gap-3 px-4 py-4">
      <button
        class="flex size-11 items-center justify-center rounded-xl text-ink-400 hover:bg-ink-100 hover:text-ink-700"
        aria-label="Back"
        @click="back"
      >
        <Icon name="back" />
      </button>
      <ProgressBar :percent="(step / steps.length) * 100" />
    </header>

    <main class="flex-1 overflow-x-hidden overflow-y-auto">
      <Transition name="slide" mode="out-in">
        <div :key="current" class="mx-auto flex w-full max-w-md flex-col gap-5 px-4 py-6">
          <form
            v-if="current === 'request'"
            id="intake-step"
            class="flex flex-col gap-5"
            @submit.prevent="request.trim() && step++"
          >
            <h2 class="text-2xl">What do you want to learn?</h2>
            <input
              v-model="request"
              :class="inputClass"
              maxlength="500"
              placeholder="e.g. SQL, music theory, the French Revolution"
              autofocus
            />
          </form>

          <form
            v-else-if="current === 'specific'"
            id="intake-step"
            class="flex flex-col gap-5"
            @submit.prevent="start"
          >
            <h2 class="text-2xl">Anything specific?</h2>
            <p class="text-ink-600">An exam, a project or a tool you have in mind. Optional.</p>
            <input
              v-model="specific"
              :class="inputClass"
              maxlength="300"
              placeholder="e.g. AP Calculus BC, or a Discord bot"
              autofocus
            />
            <p v-if="error" class="text-coral-600">Couldn't start this topic: {{ error }}</p>
          </form>

          <template v-else>
            <h2 class="text-2xl">{{ question.question }}</h2>
            <div class="flex flex-col gap-3">
              <button
                v-for="option in question.options"
                :key="option.value"
                :class="choiceClass(answers[question.key].value === option.value)"
                @click="pick(option.value)"
              >
                <span class="flex flex-col">
                  <span class="font-extrabold">{{ option.label }}</span>
                  <span class="text-base text-ink-500">{{ option.detail }}</span>
                </span>
              </button>
            </div>
          </template>
        </div>
      </Transition>
    </main>

    <!-- The typed steps go on with a button at the bottom; the choices, when one is tapped -->
    <footer
      v-if="current === 'request' || current === 'specific'"
      class="safe-bottom border-t-2 border-ink-200 px-4 pt-5"
    >
      <div class="mx-auto max-w-md">
        <PupilButton
          v-if="current === 'request'"
          type="submit"
          form="intake-step"
          block
          :disabled="!request.trim()"
        >
          Continue
        </PupilButton>
        <PupilButton v-else type="submit" form="intake-step" block :disabled="busy">
          {{ busy ? 'Starting…' : specific.trim() ? 'Start learning' : 'Skip and start' }}
        </PupilButton>
      </div>
    </footer>
  </div>
</template>
