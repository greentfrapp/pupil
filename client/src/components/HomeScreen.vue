<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listTopics, type Topic } from '../api/topics'
import Icon from './ui/Icon.vue'
import ProgressBar from './ui/ProgressBar.vue'
import PupilButton from './ui/PupilButton.vue'

const emit = defineEmits<{ open: [topicId: string]; learn: [] }>()

const topics = ref<Topic[] | null>(null)
const error = ref<string | null>(null)

async function load() {
  error.value = null
  try {
    topics.value = await listTopics()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(load)

/** Lessons taken, out of the stops on the path. */
function counts(topic: Topic): { done: number; stops: number } {
  const done = topic.lessons.filter((l) => l.purpose === 'lesson' && l.attempts > 0).length
  const stops = topic.path.reduce((n, u) => n + u.stops, 0)
  return { done, stops }
}

function progress(topic: Topic): string {
  if (topic.finished) return 'Finished'
  if (!topic.syllabus) return 'Getting started'
  const { done, stops } = counts(topic)
  return `${done} of ${stops} lessons done`
}

function percent(topic: Topic): number {
  const { done, stops } = counts(topic)
  return stops ? (done / stops) * 100 : 0
}
</script>

<template>
  <main class="mx-auto flex min-h-dvh max-w-md flex-col gap-6 px-4 py-16">
    <PupilButton variant="primary" block @click="emit('learn')">
      Learn something new
      <Icon name="plus" weight="bold" :size="18" />
    </PupilButton>

    <p v-if="error" class="text-coral-600">
      Couldn't load your topics: {{ error }}
      <button class="font-bold underline" @click="load">Try again</button>
    </p>
    <p v-else-if="!topics" class="text-ink-500">Loading…</p>
    <template v-else-if="topics.length">
      <h2 class="text-xl">Continue learning</h2>
      <ul class="flex flex-col gap-3">
        <li v-for="topic in topics" :key="topic.id">
          <button
            class="flex w-full items-center gap-4 rounded-2xl border-2 border-ink-200 bg-white px-4 py-4 text-left hover:bg-ink-50"
            @click="emit('open', topic.id)"
          >
            <div
              v-if="topic.finished"
              class="flex size-14 shrink-0 items-center justify-center rounded-full bg-sun-400 text-white"
            >
              <Icon name="trophy" :size="28" label="Finished" />
            </div>
            <div class="flex min-w-0 flex-1 flex-col gap-1">
              <span class="truncate text-lg font-extrabold">{{ topic.request }}</span>
              <span class="text-ink-500">{{ progress(topic) }}</span>
              <div v-if="!topic.finished" class="mt-1 flex">
                <ProgressBar :percent="percent(topic)" />
              </div>
            </div>
          </button>
        </li>
      </ul>
    </template>
    <p v-else class="text-center text-lg text-ink-500">
      Pick anything you're curious about. Pupil writes the lessons for you.
    </p>
  </main>
</template>
