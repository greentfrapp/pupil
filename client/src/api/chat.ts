// Mirrors pupil_server.agents.base.AgentEvent.
export type AgentEvent =
  | { type: 'text_delta'; text: string }
  | { type: 'tool_call'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; id: string; output: unknown; is_error: boolean }
  | { type: 'turn_complete'; cost_usd: number | null; usage: Record<string, unknown> | null }
  | { type: 'error'; message: string }

// Mirrors pupil_server.conversations.transcript.TranscriptItem: agent events as they were
// streamed, with each run of text merged into one text_delta.
export type TranscriptItem = { type: 'user_message'; text: string } | AgentEvent

export interface Conversation {
  conversation_id: string
  created_at: string
  transcript: TranscriptItem[]
}

export class NotFound extends Error {}

async function failure(res: Response): Promise<Error> {
  const body = await res.json().catch(() => null)
  const message = body?.detail ?? `HTTP ${res.status}`
  return res.status === 404 ? new NotFound(message) : new Error(message)
}

export async function startConversation(): Promise<string> {
  const res = await fetch('/api/conversations', { method: 'POST' })
  if (!res.ok) throw await failure(res)
  return (await res.json()).conversation_id
}

export async function getConversation(id: string): Promise<Conversation> {
  const res = await fetch(`/api/conversations/${id}`)
  if (!res.ok) throw await failure(res)
  return res.json()
}

/** Let the server close the live agent session; the conversation can carry on later. */
export async function releaseSession(id: string): Promise<void> {
  await fetch(`/api/conversations/${id}/session`, { method: 'DELETE', keepalive: true })
}

/** Send one message and call `onEvent` for each event as it streams in. */
export async function sendMessage(
  id: string,
  text: string,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  // EventSource only does GET, so read the SSE stream from fetch directly.
  const res = await fetch(`/api/conversations/${id}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!res.ok || !res.body) throw await failure(res)

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    let end
    while ((end = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)
      for (const line of frame.split('\n')) {
        if (line.startsWith('data: ')) onEvent(JSON.parse(line.slice(6)))
      }
    }
  }
}
