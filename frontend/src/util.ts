import type { LessonSummary, StepName } from './types'

export function ago(ts: number | null | undefined): string {
  if (!ts) return ''
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 45) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

export function stamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function duration(sec?: number | null): string {
  if (!sec) return ''
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

export const STEP_ORDER: StepName[] = ['research', 'draft', 'qc_facts', 'qc_teaching']

/** One short phrase for the sidebar. */
export function lessonState(l: Pick<LessonSummary, 'steps'>): { label: string; tone: 'busy' | 'bad' | 'ok' | 'idle' } {
  const steps = STEP_ORDER.map((s) => l.steps[s])
  if (steps.some((s) => s.status === 'running' || s.status === 'pending')) {
    const running = STEP_ORDER.find((s) => l.steps[s].status === 'running')
    const label = { research: 'Researching', draft: 'Writing', qc_facts: 'Fact-checking', qc_teaching: 'Reviewing' }
    return { label: running ? `${label[running]}…` : 'Queued…', tone: 'busy' }
  }
  if (steps.some((s) => s.status === 'failed')) return { label: 'Needs attention', tone: 'bad' }
  if (steps.every((s) => s.status === 'done')) return { label: 'Reviewed', tone: 'ok' }
  return { label: 'Draft', tone: 'idle' }
}

export function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeStorage(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, value)
  } catch {
    /* storage unavailable: the server copy is still safe */
  }
}
