<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  getConversation,
  NotFound,
  releaseSession,
  sendMessage,
  startConversation,
  type AgentEvent,
  type TranscriptItem,
} from '../api/chat'
import LessonPlayer from './LessonPlayer.vue'

type Part =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; id: string; name: string; status: 'running' | 'ok' | 'error' }
  | { kind: 'lesson'; lessonId: string }

interface Message {
  role: 'user' | 'agent'
  parts: Part[]
  error?: string
}

const roleStyle = {
  user: 'self-end bg-blue-50',
  agent: 'self-start bg-gray-100',
} satisfies Record<Message['role'], string>

/** The lesson open in the lesson player, if any. */
const openLesson = ref<string | null>(null)

const messages = ref<Message[]>([])
const draft = ref('')
const busy = ref(false)
const log = ref<HTMLElement | null>(null)
let conversationId: string | null = null

// Remembered per browser, so a reload carries on with the same conversation.
const STORAGE_KEY = 'pupil.conversation'

function remember(id: string | null) {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Storage can be unavailable (e.g. private windows); the chat still works without it.
  }
}

function remembered(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

const toolStyle = {
  running: 'opacity-60',
  ok: '',
  error: 'text-red-600',
} satisfies Record<Extract<Part, { kind: 'tool' }>['status'], string>

function apply(message: Message, event: AgentEvent) {
  const last = message.parts[message.parts.length - 1]
  switch (event.type) {
    case 'text_delta':
      if (last?.kind === 'text') last.text += event.text
      else message.parts.push({ kind: 'text', text: event.text })
      break
    case 'tool_call':
      message.parts.push({ kind: 'tool', id: event.id, name: event.name, status: 'running' })
      break
    case 'tool_result': {
      const part = message.parts.find((p) => p.kind === 'tool' && p.id === event.id)
      if (part?.kind !== 'tool') break
      part.status = event.is_error ? 'error' : 'ok'
      const lessonId =
        part.name === 'create_lesson' && !event.is_error && lessonIdFrom(event.output)
      if (lessonId) message.parts.push({ kind: 'lesson', lessonId })
      break
    }
    case 'error':
      message.error = event.message
      break
  }
}

/** The lesson id in create_lesson's result, which arrives as JSON text from some backends. */
function lessonIdFrom(output: unknown): string | null {
  let value = output
  if (typeof value === 'string') {
    try {
      value = JSON.parse(value)
    } catch {
      return null
    }
  }
  const id = (value as { lesson_id?: unknown } | null)?.lesson_id
  return typeof id === 'string' ? id : null
}

async function send() {
  const text = draft.value.trim()
  if (!text || busy.value) return
  draft.value = ''
  busy.value = true
  messages.value.push({ role: 'user', parts: [{ kind: 'text', text }] })
  messages.value.push({ role: 'agent', parts: [] })
  // Mutate through the reactive array so the view updates as events arrive.
  const reply = messages.value[messages.value.length - 1]
  try {
    if (!conversationId) {
      conversationId = await startConversation()
      remember(conversationId)
    }
    await sendMessage(conversationId, text, (event) => {
      apply(reply, event)
      scrollDown()
    })
  } catch (e) {
    reply.error = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

/** Rebuild the messages from a saved transcript, through the same `apply` as a live turn. */
function replay(transcript: TranscriptItem[]): Message[] {
  const restored: Message[] = []
  for (const item of transcript) {
    if (item.type === 'user_message') {
      restored.push({ role: 'user', parts: [{ kind: 'text', text: item.text }] })
      continue
    }
    let reply = restored[restored.length - 1]
    if (reply?.role !== 'agent') {
      reply = { role: 'agent', parts: [] }
      restored.push(reply)
    }
    apply(reply, item)
  }
  return restored
}

async function restore(id: string) {
  busy.value = true
  try {
    const conversation = await getConversation(id)
    conversationId = id
    messages.value = replay(conversation.transcript)
    scrollDown()
  } catch (e) {
    if (e instanceof NotFound) remember(null)
    else messages.value = [{ role: 'agent', parts: [], error: `Could not load the chat: ${e}` }]
  } finally {
    busy.value = false
  }
}

function startOver() {
  if (busy.value) return
  if (conversationId) releaseSession(conversationId)
  conversationId = null
  remember(null)
  messages.value = []
}

function scrollDown() {
  nextTick(() => log.value?.scrollTo({ top: log.value.scrollHeight }))
}

onMounted(() => {
  const id = remembered()
  if (id) restore(id)
})

onBeforeUnmount(() => {
  if (conversationId) releaseSession(conversationId)
})
</script>

<template>
  <section class="flex h-96 flex-col rounded-lg border border-gray-300">
    <div ref="log" class="flex flex-1 flex-col gap-2 overflow-y-auto p-3">
      <p v-if="!messages.length" class="text-gray-500">Say hello to your tutor.</p>
      <div
        v-for="(m, i) in messages"
        :key="i"
        :class="[
          'max-w-[85%] rounded-lg px-3 py-2 leading-snug whitespace-pre-wrap',
          roleStyle[m.role],
        ]"
      >
        <template v-for="(p, j) in m.parts" :key="j">
          <span v-if="p.kind === 'text'">{{ p.text }}</span>
          <button
            v-else-if="p.kind === 'lesson'"
            class="my-1 block rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700"
            @click="openLesson = p.lessonId"
          >
            Start the lesson
          </button>
          <span
            v-else
            :class="[
              'mx-1 my-0.5 inline-block rounded-full border border-gray-300 bg-white px-1.5 text-xs',
              toolStyle[p.status],
            ]"
          >
            ⚙ {{ p.name }}
          </span>
        </template>
        <span v-if="m.role === 'agent' && !m.parts.length && !m.error" class="text-gray-500">…</span>
        <p v-if="m.error" class="text-red-600">{{ m.error }}</p>
      </div>
    </div>
    <form class="flex gap-2 border-t border-gray-300 p-2" @submit.prevent="send">
      <input
        v-model="draft"
        :disabled="busy"
        placeholder="Ask something…"
        class="flex-1 rounded-md border border-gray-300 px-2 py-1.5 focus:border-blue-500 focus:outline-none disabled:bg-gray-50"
      />
      <button
        :disabled="busy || !draft.trim()"
        class="rounded-md bg-blue-600 px-4 py-1.5 text-white hover:bg-blue-700 disabled:opacity-50"
      >
        Send
      </button>
      <button
        type="button"
        :disabled="busy || !messages.length"
        class="rounded-md border border-gray-300 px-3 py-1.5 hover:bg-gray-50 disabled:opacity-50"
        @click="startOver"
      >
        New chat
      </button>
    </form>
    <LessonPlayer v-if="openLesson" :lesson-id="openLesson" @close="openLesson = null" />
  </section>
</template>
