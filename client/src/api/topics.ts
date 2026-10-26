// Mirrors pupil_server.api.topics: what the learner asked to learn, and what the agent has
// prepared for it so far.

import { getJson, postJson } from './http'

export type Why = 'work' | 'exam' | 'build' | 'curiosity'
export type Depth = 'overview' | 'working' | 'expert'
export type Level = 'new' | 'basics' | 'well'

/** The learner's answers to the setup questions. */
export interface Profile {
  why: Why
  depth: Depth
  level: Level
  specific: string | null
}

export interface Syllabus {
  id: string
  topic: string
  goal: string
  /** Why the plan looks the way it does, in a line for the learner. */
  rationale: string | null
  revision: number
}

export interface LessonSummary {
  lesson_id: string
  title: string
  purpose: 'placement' | 'lesson'
  questions: number
  attempts: number
  /** How many questions the latest attempt got right; null if not taken yet. */
  latest_correct: number | null
}

/** A unit of the syllabus, with its lessons as stops on the path. */
export interface PathUnit {
  unit_id: string
  title: string
  summary: string
  /** How many lessons the unit takes. */
  stops: number
  /** The lessons written for it so far, oldest first; the rest of its stops are to come. */
  lesson_ids: string[]
}

export type Job = 'placement' | 'plan' | 'next_lesson' | 'extend'

export interface RunStatus {
  job: Job
  state: 'running' | 'done' | 'failed'
  error: string | null
}

export interface Topic {
  id: string
  request: string
  profile: Profile
  created_at: string
  syllabus: Syllabus | null
  /** Oldest first. */
  lessons: LessonSummary[]
  /** The syllabus's units in learning order, with their lessons; empty without one. */
  path: PathUnit[]
  /** The oldest lesson not taken yet, if any. */
  next_lesson_id: string | null
  /** Every lesson on the path has been taken. */
  finished: boolean
  last_run: RunStatus | null
}

/** Start a topic; the agent starts preparing it straight away. */
export function createTopic(request: string, profile: Profile): Promise<Topic> {
  return postJson('/api/topics', { request, profile })
}

/** The learner's topics, newest first. */
export function listTopics(): Promise<Topic[]> {
  return getJson('/api/topics')
}

export function getTopic(id: string): Promise<Topic> {
  return getJson(`/api/topics/${id}`)
}

/** Start the run the topic needs, e.g. to try again after one failed. */
export function prepareTopic(id: string): Promise<Topic> {
  return postJson(`/api/topics/${id}/prepare`)
}

/** Go further than a finished topic's path: the agent adds units, then their lessons. */
export function extendTopic(id: string): Promise<Topic> {
  return postJson(`/api/topics/${id}/extend`)
}
