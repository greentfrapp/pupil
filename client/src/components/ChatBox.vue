<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref } from 'vue'
import { createSession, deleteSession, sendMessage, type AgentEvent } from '../api/chat'

type Part =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; id: string; name: string; status: 'running' | 'ok' | 'error' }

interface Message {
  role: 'user' | 'agent'
  parts: Part[]
  error?: string
}

const messages = ref<Message[]>([])
const draft = ref('')
const busy = ref(false)
const log = ref<HTMLElement | null>(null)
let sessionId: string | null = null

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
      if (part?.kind === 'tool') part.status = event.is_error ? 'error' : 'ok'
      break
    }
    case 'error':
      message.error = event.message
      break
  }
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
    sessionId ??= await createSession()
    await sendMessage(sessionId, text, (event) => {
      apply(reply, event)
      scrollDown()
    })
  } catch (e) {
    reply.error = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

function scrollDown() {
  nextTick(() => log.value?.scrollTo({ top: log.value.scrollHeight }))
}

onBeforeUnmount(() => {
  if (sessionId) deleteSession(sessionId)
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
          m.role === 'user' ? 'self-end bg-blue-50' : 'self-start bg-gray-100',
        ]"
      >
        <template v-for="(p, j) in m.parts" :key="j">
          <span v-if="p.kind === 'text'">{{ p.text }}</span>
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
    </form>
  </section>
</template>
