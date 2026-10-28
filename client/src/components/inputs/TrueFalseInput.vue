<script setup lang="ts">
import { ref } from 'vue'
import type { LessonResponse } from '../../api/lessons'
import type { Mark } from '../../grading'
import { choiceClass } from './styles'

defineProps<{ disabled: boolean; marks?: Record<string, Mark> | null }>()
const response = defineModel<LessonResponse | null>({ required: true })

const picked = ref<boolean | null>(null)

function pick(value: boolean) {
  picked.value = value
  response.value = { kind: 'bool', value }
}
</script>

<template>
  <div class="flex gap-2">
    <button
      v-for="value in [true, false]"
      :key="String(value)"
      :disabled="disabled"
      :class="[choiceClass(picked === value, marks?.[String(value)]), 'justify-center']"
      @click="pick(value)"
    >
      {{ value ? 'True' : 'False' }}
    </button>
  </div>
</template>
