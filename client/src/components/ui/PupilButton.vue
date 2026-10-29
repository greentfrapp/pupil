<script setup lang="ts">
// A chunky, rounded button that darkens on hover.

withDefaults(
  defineProps<{
    variant?: "primary" | "success" | "secondary" | "danger" | "ghost";
    /** As wide as its container, as on a phone. */
    block?: boolean;
    type?: "button" | "submit";
  }>(),
  { variant: "primary", block: false, type: "button" },
);

const looks = {
  primary: "bg-sun-400 text-ink-900 hover:bg-sun-500",
  success: "bg-leaf-500 text-white hover:bg-leaf-600",
  danger: "bg-coral-500 text-white hover:bg-coral-600",
  secondary:
    "border-2 border-ink-200 bg-white text-lake-600 hover:bg-ink-50",
  ghost: "text-lake-600 hover:bg-lake-50",
};
</script>

<template>
  <button
    :type="type"
    :class="[
      'inline-flex min-h-12 items-center justify-center gap-2 rounded-2xl px-6 py-3 text-base font-extrabold tracking-wide uppercase select-none',
      'disabled:pointer-events-none disabled:border-0 disabled:bg-ink-200 disabled:text-ink-400',
      looks[variant],
      block && 'w-full',
    ]"
  >
    <slot />
  </button>
</template>
