<script setup lang="ts">
import { computed, ref } from 'vue'
import { createTopic, type Depth, type Level, type Why } from '../api/topics'
import { DEPTH, LEVEL, WHY } from '../setup'
import { choiceClass, inputClass } from './inputs/styles'

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

const buttonClass =
  'self-end rounded-xl bg-blue-600 px-6 py-3 text-lg font-semibold text-white hover:bg-blue-700 disabled:opacity-40'
</script>

<template>
  <div class="fixed inset-0 z-10 flex flex-col bg-white">
    <header class="flex items-center gap-4 px-4 py-4">
      <button class="text-2xl text-gray-400 hover:text-gray-700" aria-label="Back" @click="back">
        ←
      </button>
      <div class="h-3 flex-1 overflow-hidden rounded-full bg-gray-200">
        <div
          class="h-full rounded-full bg-green-500 transition-all"
          :style="{ width: `${(step / steps.length) * 100}%` }"
        />
      </div>
    </header>

    <main class="mx-auto flex w-full max-w-xl flex-1 flex-col gap-5 overflow-y-auto px-4 py-6">
      <form
        v-if="current === 'request'"
        class="flex flex-col gap-5"
        @submit.prevent="request.trim() && step++"
      >
        <h2 class="text-2xl font-bold">What do you want to learn?</h2>
        <input
          v-model="request"
          :class="inputClass"
          maxlength="500"
          placeholder="e.g. SQL, music theory, the French Revolution"
          autofocus
        />
        <button :disabled="!request.trim()" :class="buttonClass">Continue</button>
      </form>

      <template v-else-if="current === 'specific'">
        <h2 class="text-2xl font-bold">Anything specific?</h2>
        <p class="text-gray-600">An exam, a project or a tool you have in mind. Optional.</p>
        <form class="flex flex-col gap-5" @submit.prevent="start">
          <input
            v-model="specific"
            :class="inputClass"
            maxlength="300"
            placeholder="e.g. AP Calculus BC, or a Discord bot"
            autofocus
          />
          <p v-if="error" class="text-red-600">Couldn't start this topic: {{ error }}</p>
          <button :disabled="busy" :class="buttonClass">
            {{ busy ? 'Starting…' : specific.trim() ? 'Start learning' : 'Skip and start' }}
          </button>
        </form>
      </template>

      <template v-else>
        <h2 class="text-2xl font-bold">{{ question.question }}</h2>
        <div class="flex flex-col gap-2">
          <button
            v-for="option in question.options"
            :key="option.value"
            :class="choiceClass(answers[question.key].value === option.value)"
            @click="pick(option.value)"
          >
            <span class="flex flex-col">
              <span class="font-semibold">{{ option.label }}</span>
              <span class="text-base text-gray-500">{{ option.detail }}</span>
            </span>
          </button>
        </div>
      </template>
    </main>
  </div>
</template>
