<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listTopics, type Topic } from '../api/topics'

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

function progress(topic: Topic): string {
  if (topic.finished) return 'Finished'
  if (!topic.syllabus) return 'Getting started'
  const done = topic.lessons.filter((l) => l.purpose === 'lesson' && l.attempts > 0).length
  const stops = topic.path.reduce((n, u) => n + u.stops, 0)
  return `${done} of ${stops} lessons done`
}
</script>

<template>
  <main class="mx-auto flex max-w-xl flex-col gap-5 px-4 py-10">
    <h1 class="text-3xl font-bold">Pupil</h1>
    <button
      class="rounded-xl bg-blue-600 px-6 py-3 text-lg font-semibold text-white hover:bg-blue-700"
      @click="emit('learn')"
    >
      Learn something new
    </button>

    <p v-if="error" class="text-red-600">
      Couldn't load your topics: {{ error }}
      <button class="underline" @click="load">Try again</button>
    </p>
    <p v-else-if="!topics" class="text-gray-500">Loading…</p>
    <ul v-else class="flex flex-col gap-2">
      <li v-for="topic in topics" :key="topic.id">
        <button
          class="flex w-full flex-col rounded-xl border-2 border-gray-200 px-4 py-3 text-left hover:bg-gray-50"
          @click="emit('open', topic.id)"
        >
          <span class="text-lg font-semibold">{{ topic.request }}</span>
          <span class="text-gray-500">{{ progress(topic) }}</span>
        </button>
      </li>
    </ul>
  </main>
</template>
