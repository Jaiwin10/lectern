export type StepName = 'research' | 'draft' | 'qc_facts' | 'qc_teaching'
export type StepStatus = 'idle' | 'pending' | 'running' | 'done' | 'failed' | 'blocked'

export interface Step {
  status: StepStatus
  error: string | null
  started_at: number | null
  finished_at: number | null
}

export interface WebSource {
  id: string
  kind: 'web'
  title: string
  url: string
  domain: string
  tier: 'high' | 'good' | 'fair' | 'unknown' | 'low'
  tier_label: string
  content: string
  provider: string
  query?: string
}

export interface Book {
  id: string
  kind: 'book'
  title: string
  authors: string[]
  year?: string
  publisher?: string
  url: string
  description?: string
  provider: string
}

export interface Video {
  id: string
  kind: 'video'
  video_id: string
  title: string
  channel?: string
  url: string
  duration_sec?: number | null
  views?: number | null
  verified: boolean
  provider: string
}

export interface Research {
  queries: string[]
  web: WebSource[]
  books: Book[]
  videos: Video[]
  notes: string[]
  providers: Record<string, string>
  collected_at: number
}

export interface Issue {
  id: string
  severity: 'high' | 'medium' | 'low'
  category: string
  location: string
  excerpt: string
  problem: string
  suggestion: string
  fix: { type: 'replace' | 'insert_after' | 'none'; text: string }
  status: 'open' | 'applied' | 'dismissed'
  applicable?: boolean
}

export interface Check {
  id: string
  label: string
  status: 'pass' | 'warn' | 'fail'
  detail: string
}

export interface Claim {
  claim: string
  verdict: 'supported' | 'well_established' | 'unsupported' | 'misleading' | 'incorrect'
  sources: string[]
  note: string
}

interface ReportBase {
  summary: string
  issues: Issue[]
  checks: Check[]
  content_hash: string
  ran_at: number
  model: string
  stale?: boolean
}

export interface FactsReport extends ReportBase {
  score: number | null
  claims: Claim[]
  source_review: { source_id: string; relevance: string; reliability: string; note: string }[]
  gaps: string[]
}

export interface TeachingReport extends ReportBase {
  score: number | null
  coverage: { component: string; coverage: 'full' | 'partial' | 'missing'; where: string; practiced: boolean; note: string }[]
  rubric: { dimension: string; score: number; reason: string }[]
  strengths: string[]
}

export interface TimingSection {
  heading: string
  planned: number | null
  words: number
  code_lines: number
  reading: number
  estimated: number
  kind: 'activity' | 'reading'
  optional: boolean
}

export interface Timing {
  sections: TimingSection[]
  planned_total: number
  estimated_total: number
  words: number
  wpm: number
  target: number
  fits: boolean
  warnings: string[]
}

export interface Lesson {
  id: string
  title: string
  objective: string
  audience: string
  content: string
  research: Research | null
  qc_facts: FactsReport | null
  qc_teaching: TeachingReport | null
  steps: Record<StepName, Step>
  created_at: number
  updated_at: number
  timing: Timing | null
  busy: boolean
  version_count: number
}

export interface LessonSummary {
  id: string
  title: string
  objective: string
  steps: Record<StepName, Step>
  created_at: number
  updated_at: number
}

export interface Version {
  id: number
  note: string
  author: 'ai' | 'instructor' | 'qc'
  created_at: number
  size: number
  content?: string
}

export interface ServerStatus {
  llm: { provider: string; model: string; qc_model: string; configured: boolean }
  research: { web: string; videos: string; books_provider: string }
}

export type Layer = 'facts' | 'teaching'
