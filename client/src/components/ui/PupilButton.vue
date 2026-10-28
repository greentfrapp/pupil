<script setup lang="ts">
// A chunky button with a darker bottom edge that it presses down into.

withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
    /** As wide as its container, as on a phone. */
    block?: boolean
    type?: 'button' | 'submit'
  }>(),
  { variant: 'primary', block: false, type: 'button' },
)

const looks = {
  primary: 'bg-leaf-500 text-white hover:bg-leaf-400 [--edge:var(--color-leaf-700)]',
  danger: 'bg-coral-500 text-white hover:bg-coral-400 [--edge:var(--color-coral-700)]',
  secondary:
    'border-2 border-ink-200 bg-white text-lake-600 hover:bg-ink-50 [--edge:var(--color-ink-200)]',
  ghost: 'text-lake-600 hover:bg-lake-50 [--edge:transparent]',
}
</script>

<template>
  <button
    :type="type"
    :class="[
      'inline-flex min-h-12 items-center justify-center gap-2 rounded-2xl px-6 py-3 text-base font-extrabold tracking-wide uppercase select-none',
      'shadow-[0_4px_0_var(--edge)] transition-[transform,box-shadow] duration-75',
      'active:translate-y-1 active:shadow-none',
      'disabled:pointer-events-none disabled:border-0 disabled:bg-ink-200 disabled:text-ink-400 disabled:[--edge:var(--color-ink-300)]',
      looks[variant],
      block && 'w-full',
    ]"
  >
    <slot />
  </button>
</template>
