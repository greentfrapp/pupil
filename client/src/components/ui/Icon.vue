<script lang="ts">
export type IconName =
  'back' | 'book' | 'check' | 'close' | 'lock' | 'plus' | 'retry' | 'star' | 'trophy'
export type IconWeight = 'thin' | 'light' | 'regular' | 'bold' | 'fill' | 'duotone'
</script>

<script setup lang="ts">
// Pupil's icons, from Phosphor (phosphor-icons.com, MIT), in the current text colour.

import {
  PhArrowCounterClockwise,
  PhBookOpen,
  PhCaretLeft,
  PhCheck,
  PhLock,
  PhPlus,
  PhStar,
  PhTrophy,
  PhX,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'

const props = withDefaults(
  defineProps<{ name: IconName; size?: number; label?: string; weight?: IconWeight }>(),
  { size: 24 },
)

/** Each icon, and its weight unless the caller picks one. Bold suits the chunky buttons. */
const ICONS: Record<IconName, { icon: Component; weight: IconWeight }> = {
  back: { icon: PhCaretLeft, weight: 'bold' },
  book: { icon: PhBookOpen, weight: 'bold' },
  check: { icon: PhCheck, weight: 'bold' },
  close: { icon: PhX, weight: 'bold' },
  lock: { icon: PhLock, weight: 'bold' },
  plus: { icon: PhPlus, weight: 'bold' },
  retry: { icon: PhArrowCounterClockwise, weight: 'bold' },
  star: { icon: PhStar, weight: 'fill' },
  trophy: { icon: PhTrophy, weight: 'bold' },
}
</script>

<template>
  <component
    :is="ICONS[name].icon"
    :size="size"
    :weight="props.weight ?? ICONS[name].weight"
    :role="label ? 'img' : undefined"
    :aria-label="label"
    :aria-hidden="label ? undefined : 'true'"
  />
</template>
