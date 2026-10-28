<script setup lang="ts">
// A thick progress bar, with a highlight along its fill.

defineProps<{ /** 0 to 100. */ percent: number }>()
</script>

<template>
  <div
    class="h-4 flex-1 overflow-hidden rounded-full bg-ink-200"
    role="progressbar"
    :aria-valuenow="Math.round(percent)"
    aria-valuemin="0"
    aria-valuemax="100"
  >
    <div
      class="h-full rounded-full bg-leaf-500 px-2 pt-1 transition-[width] duration-500 ease-out"
      :style="{ width: `${percent}%` }"
    >
      <div v-if="percent > 4" class="h-1 rounded-full bg-white/35" />
    </div>
  </div>
</template>
