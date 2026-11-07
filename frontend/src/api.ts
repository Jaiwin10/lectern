import type { Layer, Lesson, LessonSummary, ServerStatus, StepName, Version } from './types'

export class ApiError extends Error {
  status: number
  fields?: Record<string, string>
  constructor(message: string, status: number, fields?: Record<string, string>) {
    super(message)
    this.status = status
    this.fields = fields
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError('Cannot reach the server. Check that it is running, then try again.', 0)
  }
  if (!res.ok) {
    let detail: unknown
    try {
      detail = (await res.json()).detail
    } catch {
      /* not JSON */
    }
    if (typeof detail === 'string') throw new ApiError(detail, res.status)
    if (detail && typeof detail === 'object' && 'message' in detail) {
      const d = detail as { message: string; fields?: Record<string, string> }
      throw new ApiError(d.message, res.status, d.fields)
    }
    throw new ApiError(`The server returned an error (${res.status}). Try again.`, res.status)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  status: () => request<ServerStatus>('/status'),
  lessons: () => request<LessonSummary[]>('/lessons'),
  create: (title: string, objective: string, audience: string) =>
    request<Lesson>('/lessons', json({ title, objective, audience })),
  lesson: (id: string) => request<Lesson>(`/lessons/${id}`),
  remove: (id: string) => request<void>(`/lessons/${id}`, { method: 'DELETE' }),
  save: (id: string, content: string, note = '') =>
    request<Lesson>(`/lessons/${id}/content`, { method: 'PUT', body: JSON.stringify({ content, note }) }),
  run: (id: string, step: StepName) => request<Lesson>(`/lessons/${id}/run`, json({ step })),
  issue: (id: string, layer: Layer, issueId: string, action: 'apply' | 'apply-ai' | 'dismiss' | 'reopen') =>
    request<Lesson>(`/lessons/${id}/qc/${layer}/issues/${issueId}/${action}`, { method: 'POST' }),
  versions: (id: string) => request<Version[]>(`/lessons/${id}/versions`),
  version: (id: string, versionId: number) => request<Version>(`/lessons/${id}/versions/${versionId}`),
  restore: (id: string, versionId: number) =>
    request<Lesson>(`/lessons/${id}/versions/${versionId}/restore`, { method: 'POST' }),
  exportUrl: (id: string, kind: string) => `/api/lessons/${id}/export/${kind}`,
}

export function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong. Try again.'
}
