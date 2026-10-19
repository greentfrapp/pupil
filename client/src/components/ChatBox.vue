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
  <section class="chat">
    <div ref="log" class="log">
      <p v-if="!messages.length" class="hint">Say hello to your tutor.</p>
      <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
        <template v-for="(p, j) in m.parts" :key="j">
          <span v-if="p.kind === 'text'">{{ p.text }}</span>
          <span v-else :class="['tool', p.status]">⚙ {{ p.name }}</span>
        </template>
        <span v-if="m.role === 'agent' && !m.parts.length && !m.error" class="hint">…</span>
        <p v-if="m.error" class="error">{{ m.error }}</p>
      </div>
    </div>
    <form @submit.prevent="send">
      <input v-model="draft" :disabled="busy" placeholder="Ask something…" />
      <button :disabled="busy || !draft.trim()">Send</button>
    </form>
  </section>
</template>

<style scoped>
.chat {
  border: 1px solid #ddd;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  height: 24rem;
}
.log {
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.msg {
  max-width: 85%;
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  white-space: pre-wrap;
  line-height: 1.4;
}
.msg.user {
  align-self: flex-end;
  background: #e8f0fe;
}
.msg.agent {
  align-self: flex-start;
  background: #f3f3f3;
}
.tool {
  display: inline-block;
  margin: 0.15rem 0.25rem;
  padding: 0 0.4rem;
  border-radius: 999px;
  font-size: 0.8em;
  background: #fff;
  border: 1px solid #ccc;
}
.tool.running {
  opacity: 0.6;
}
.tool.error,
.error {
  color: #c0392b;
}
.hint {
  color: #888;
}
form {
  display: flex;
  gap: 0.5rem;
  padding: 0.5rem;
  border-top: 1px solid #ddd;
}
input {
  flex: 1;
  padding: 0.4rem;
}
</style>
