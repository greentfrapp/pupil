<script setup lang="ts">
import { ref } from 'vue'
import HomeScreen from './components/HomeScreen.vue'
import IntakeFlow from './components/IntakeFlow.vue'
import LessonPlayer from './components/LessonPlayer.vue'
import TopicScreen from './components/TopicScreen.vue'

type View =
  | { name: 'home' }
  | { name: 'intake' }
  | { name: 'topic'; topicId: string }
  | { name: 'lesson'; topicId: string; lessonId: string }

const view = ref<View>({ name: 'home' })

function openLesson(lessonId: string) {
  if (view.value.name === 'topic') {
    view.value = { name: 'lesson', topicId: view.value.topicId, lessonId }
  }
}

/** Back to the topic, which shows what the agent is preparing next. */
function closeLesson() {
  if (view.value.name === 'lesson') view.value = { name: 'topic', topicId: view.value.topicId }
}
</script>

<template>
  <div class="min-h-screen bg-white font-sans text-gray-900">
    <HomeScreen
      v-if="view.name === 'home'"
      @learn="view = { name: 'intake' }"
      @open="(topicId) => (view = { name: 'topic', topicId })"
    />
    <IntakeFlow
      v-else-if="view.name === 'intake'"
      @close="view = { name: 'home' }"
      @created="(topicId) => (view = { name: 'topic', topicId })"
    />
    <TopicScreen
      v-else-if="view.name === 'topic'"
      :topic-id="view.topicId"
      @close="view = { name: 'home' }"
      @play="openLesson"
    />
    <LessonPlayer
      v-else
      :key="view.lessonId"
      :lesson-id="view.lessonId"
      @close="closeLesson"
    />
  </div>
</template>
