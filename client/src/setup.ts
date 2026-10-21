// The fixed setup questions asked when the learner starts a topic. Written into the app, not
// by the agent, so they're instant and free; the agent's instructions say what each answer
// changes (pupil_server.runs.jobs).

import type { Depth, Level, Why } from './api/topics'

export interface SetupQuestion<T extends string> {
  key: 'why' | 'depth' | 'level'
  question: string
  options: { value: T; label: string; detail: string }[]
}

export const WHY: SetupQuestion<Why> = {
  key: 'why',
  question: 'Why are you learning this?',
  options: [
    { value: 'work', label: 'For work', detail: 'Practical tasks first' },
    { value: 'exam', label: 'For a course or exam', detail: 'The standard curriculum' },
    { value: 'build', label: 'To build something', detail: 'What your project needs next' },
    { value: 'curiosity', label: 'Curiosity', detail: 'Big ideas and intuition' },
  ],
}

export const DEPTH: SetupQuestion<Depth> = {
  key: 'depth',
  question: 'How far do you want to go?',
  options: [
    { value: 'overview', label: 'A quick overview', detail: 'A few units on the key ideas' },
    { value: 'working', label: 'Solid working knowledge', detail: 'Confident everyday use' },
    { value: 'expert', label: 'Deep expertise', detail: 'Advanced topics and edge cases' },
  ],
}

export const LEVEL: SetupQuestion<Level> = {
  key: 'level',
  question: 'How much do you know already?',
  options: [
    { value: 'new', label: "I'm new to this", detail: 'Start at the beginning' },
    { value: 'basics', label: 'I know the basics', detail: 'A few questions to find your level' },
    { value: 'well', label: 'I know it well', detail: 'A few questions to find your level' },
  ],
}
