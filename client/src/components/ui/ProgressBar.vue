<script setup lang="ts">
// A thick, rounded progress bar.

withDefaults(
  defineProps<{
    /** 0 to 100. */
    percent: number
    /** The fill's background class. */
    fill?: string
  }>(),
  { fill: 'bg-leaf-500' },
)
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
      :class="['h-full rounded-full transition-[width] duration-500 ease-out', fill]"
      :style="{ width: `${percent}%` }"
    />
  </div>
</template>
