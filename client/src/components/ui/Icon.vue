<script lang="ts">
export type IconName =
  | 'back'
  | 'book'
  | 'check'
  | 'close'
  | 'lock'
  | 'plus'
  | 'star'
  | 'trophy'
  | 'volume'
  | 'volume-off'
</script>

<script setup lang="ts">
// Pupil's few icons, drawn on a 24-unit grid in the current text colour.

withDefaults(defineProps<{ name: IconName; size?: number; label?: string }>(), { size: 24 })

/** Each icon's strokes; a `fill` path is filled instead of stroked. */
const ICONS: Record<IconName, { d: string; fill?: boolean }[]> = {
  back: [{ d: 'M15 5l-7 7 7 7' }],
  book: [
    { d: 'M3 5h6a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H3z' },
    { d: 'M21 5h-6a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h7z' },
  ],
  check: [{ d: 'M5 12.5l4.5 4.5L19 7.5' }],
  close: [{ d: 'M6 6l12 12M18 6L6 18' }],
  lock: [{ d: 'M6 11h12v9H6z' }, { d: 'M8.5 11V8a3.5 3.5 0 0 1 7 0v3' }],
  plus: [{ d: 'M12 5v14M5 12h14' }],
  star: [
    {
      d: 'M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9z',
      fill: true,
    },
  ],
  trophy: [
    { d: 'M8 4h8v5a4 4 0 0 1-8 0z' },
    { d: 'M8 6H5.5a2.5 2.5 0 0 0 2.5 4M16 6h2.5a2.5 2.5 0 0 1-2.5 4' },
    { d: 'M12 13v4M8.5 20h7' },
  ],
  volume: [
    { d: 'M4 10v4h4l5 4V6l-5 4z' },
    { d: 'M16.5 9.5a3.5 3.5 0 0 1 0 5M19 7a7 7 0 0 1 0 10' },
  ],
  'volume-off': [{ d: 'M4 10v4h4l5 4V6l-5 4z' }, { d: 'M17 9.5l5 5M22 9.5l-5 5' }],
}
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    stroke="currentColor"
    stroke-width="2.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    fill="none"
    :role="label ? 'img' : undefined"
    :aria-label="label"
    :aria-hidden="label ? undefined : 'true'"
  >
    <path
      v-for="(part, i) in ICONS[name]"
      :key="i"
      :d="part.d"
      :fill="part.fill ? 'currentColor' : 'none'"
      :stroke="part.fill ? 'none' : undefined"
    />
  </svg>
</template>
