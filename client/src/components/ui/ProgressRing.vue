<script setup lang="ts">
// How far through something the learner is, as a ring, with what's inside it in the slot.

import { computed } from 'vue'

const props = withDefaults(defineProps<{ /** 0 to 1. */ fraction: number; size?: number }>(), {
  size: 56,
})

const STROKE = 6
const radius = computed(() => (props.size - STROKE) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
</script>

<template>
  <div class="relative shrink-0" :style="{ width: `${size}px`, height: `${size}px` }">
    <svg :width="size" :height="size" class="-rotate-90" aria-hidden="true">
      <circle
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        :stroke-width="STROKE"
        class="stroke-ink-200"
      />
      <circle
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        :stroke-width="STROKE"
        stroke-linecap="round"
        class="stroke-leaf-500 transition-[stroke-dashoffset] duration-500"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="circumference * (1 - Math.min(Math.max(fraction, 0), 1))"
      />
    </svg>
    <div class="absolute inset-0 flex items-center justify-center">
      <slot />
    </div>
  </div>
</template>
