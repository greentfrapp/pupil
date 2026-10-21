<script setup lang="ts">
import { onMounted, ref } from 'vue'

interface Health {
  status: string
  version: string
  mode: string
}

const health = ref<Health | null>(null)
const error = ref<string | null>(null)
const loading = ref(false)

async function ping() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch('/api/health')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    health.value = await res.json()
  } catch (e) {
    health.value = null
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(ping)
</script>

<template>
  <main class="mx-auto my-16 max-w-2xl space-y-4 px-4 font-sans text-gray-900">
    <h1 class="text-3xl font-bold">Hello, Pupil</h1>
    <div class="flex items-center gap-3">
      <p v-if="loading" class="text-gray-500">Pinging sidecar…</p>
      <p v-else-if="health">
        Sidecar: <strong>{{ health.status }}</strong> (v{{ health.version }}, {{ health.mode }})
      </p>
      <p v-else class="text-red-600">Sidecar unreachable: {{ error }}</p>
      <button
        :disabled="loading"
        class="rounded-md border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50 disabled:opacity-50"
        @click="ping"
      >
        Ping again
      </button>
    </div>
  </main>
</template>
