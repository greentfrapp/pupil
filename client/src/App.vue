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
  <main>
    <h1>Hello, Pupil</h1>
    <p v-if="loading">Pinging sidecar…</p>
    <p v-else-if="health">
      Sidecar: <strong>{{ health.status }}</strong> (v{{ health.version }}, {{ health.mode }})
    </p>
    <p v-else class="error">Sidecar unreachable: {{ error }}</p>
    <button :disabled="loading" @click="ping">Ping again</button>
  </main>
</template>

<style scoped>
main {
  font-family: system-ui, sans-serif;
  max-width: 32rem;
  margin: 4rem auto;
  padding: 0 1rem;
}
.error {
  color: #c0392b;
}
</style>
