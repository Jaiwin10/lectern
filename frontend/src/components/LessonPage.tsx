import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, errorText } from '../api'
import type { Layer, Lesson, StepName } from '../types'
import { STEP_ORDER, readStorage, writeStorage } from '../util'
import { Editor } from './Editor'
import { History } from './History'
import { Preview } from './Preview'
import { Review } from './Review'
import { Sources } from './Sources'
import { Steps } from './Steps'

const TABS = [
  { key: 'lesson', label: 'Lesson' },
  { key: 'sources', label: 'Sources' },
  { key: 'facts', label: 'Fact check' },
  { key: 'teaching', label: 'Teaching review' },
  { key: 'preview', label: 'Preview & export' },
  { key: 'history', label: 'History' },
] as const

export function LessonPage({ onChanged }: { onChanged: () => void }) {
  const { id = '', tab = 'lesson' } = useParams()
  const navigate = useNavigate()
  const [lesson, setLesson] = useState<Lesson | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [draft, setDraft] = useState<string | null>(null)
  const [restored, setRestored] = useState(false)
  const [saving, setSaving] = useState(false)
  const storageKey = `lectern:unsaved:${id}`
  const lastStatus = useRef('')

  const load = useCallback(async () => {
    try {
      const l = await api.lesson(id)
      setLesson(l)
      setLoadError(null)
      const status = STEP_ORDER.map((s) => l.steps[s].status).join()
      if (status !== lastStatus.current) {
        lastStatus.current = status
        onChanged()
      }
      return l
    } catch (e) {
      setLoadError(errorText(e))
      return null
    }
  }, [id, onChanged])

  // Load the lesson; bring back unsaved edits from an earlier visit if there are any.
  useEffect(() => {
    setLesson(null)
    setDraft(null)
    setRestored(false)
    setActionError(null)
    lastStatus.current = ''
    load().then((l) => {
      const stored = readStorage(storageKey)
      if (l && stored !== null && stored !== l.content) {
        setDraft(stored)
        setRestored(true)
      }
    })
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  const active =
    !!lesson && (lesson.busy || STEP_ORDER.some((s) => ['running', 'pending'].includes(lesson.steps[s].status)))
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(load, 1500)
    return () => window.clearInterval(timer)
  }, [active, load])

  const dirty = draft !== null && lesson !== null && draft !== lesson.content
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const change = (text: string) => {
    setDraft(text)
    writeStorage(storageKey, text)
  }
  const discard = () => {
    setDraft(null)
    setRestored(false)
    writeStorage(storageKey, null)
  }
  const save = async () => {
    if (!lesson || !dirty || draft === null) return
    setSaving(true)
    setActionError(null)
    try {
      const updated = await api.save(lesson.id, draft)
      setLesson(updated)
      setDraft(null)
      setRestored(false)
      writeStorage(storageKey, null)
      onChanged()
    } catch (e) {
      setActionError(`Not saved: ${errorText(e)} Your edits are still here and kept in this browser.`)
    } finally {
      setSaving(false)
    }
  }

  const run = async (step: StepName) => {
    if (!lesson) return
    if (step === 'draft' && lesson.content) {
      const ok = window.confirm('Write a new draft from the same research? The current text stays in History.')
      if (!ok) return
    }
    setActionError(null)
    try {
      setLesson(await api.run(lesson.id, step))
      onChanged()
    } catch (e) {
      setActionError(errorText(e))
    }
  }

  const issueAction = async (layer: Layer, issueId: string, action: 'apply' | 'apply-ai' | 'dismiss' | 'reopen') => {
    if (!lesson) return
    setActionError(null)
    try {
      setLesson(await api.issue(lesson.id, layer, issueId, action))
    } catch (e) {
      setActionError(errorText(e))
    }
  }

  const remove = async () => {
    if (!lesson || !window.confirm(`Delete “${lesson.title}” and all its versions? This cannot be undone.`)) return
    try {
      await api.remove(lesson.id)
      writeStorage(storageKey, null)
      onChanged()
      navigate('/')
    } catch (e) {
      setActionError(errorText(e))
    }
  }

  if (loadError && !lesson) {
    return (
      <div className="page narrow">
        <div className="notice bad">
          <p>{loadError}</p>
          <button className="btn small" onClick={load}>
            Try again
          </button>
        </div>
      </div>
    )
  }
  if (!lesson) return <div className="page muted">Loading…</div>

  const open = (layer: 'qc_facts' | 'qc_teaching') =>
    lesson[layer]?.issues.filter((i) => i.status === 'open').length ?? 0
  const counts: Record<string, { n: number; alert?: boolean } | undefined> = {
    sources: lesson.research
      ? { n: lesson.research.web.length + lesson.research.books.length + lesson.research.videos.length }
      : undefined,
    facts: lesson.qc_facts ? { n: open('qc_facts'), alert: open('qc_facts') > 0 } : undefined,
    teaching: lesson.qc_teaching ? { n: open('qc_teaching'), alert: open('qc_teaching') > 0 } : undefined,
    history: lesson.version_count ? { n: lesson.version_count } : undefined,
  }

  return (
    <div className="page">
      <div className="lesson-head">
        <div>
          <p className="kicker">Lesson · 45 minutes</p>
          <h1 className="title">{lesson.title}</h1>
          <p className="objective">{lesson.objective}</p>
        </div>
        <div className="row">
          <button className="btn quiet danger small" onClick={remove} disabled={lesson.busy}>
            Delete
          </button>
        </div>
      </div>

      <Steps lesson={lesson} onRun={run} busy={lesson.busy} />

      {loadError && (
        <div className="notice warn" style={{ marginTop: 12 }}>
          <p>Lost contact with the server: {loadError} Retrying…</p>
        </div>
      )}
      {actionError && (
        <div className="notice bad" style={{ marginTop: 12 }}>
          <p>{actionError}</p>
          <button className="btn quiet small" onClick={() => setActionError(null)}>
            Close
          </button>
        </div>
      )}

      <nav className="tabs">
        {TABS.map((t) => {
          const c = counts[t.key]
          return (
            <Link key={t.key} to={`/lessons/${lesson.id}/${t.key}`} className={`tab ${tab === t.key ? 'active' : ''}`}>
              {t.label}
              {c && <span className={`count ${c.alert ? 'alert' : ''}`}>{c.n}</span>}
            </Link>
          )
        })}
      </nav>

      {tab === 'lesson' && (
        <Editor
          lesson={lesson}
          value={draft ?? lesson.content}
          dirty={dirty}
          saving={saving}
          restored={restored && dirty}
          onChange={change}
          onSave={save}
          onDiscard={discard}
          onRegenerate={() => run('draft')}
          busy={lesson.busy}
        />
      )}
      {tab === 'sources' && <Sources lesson={lesson} busy={lesson.busy} onRerun={() => run('research')} />}
      {(tab === 'facts' || tab === 'teaching') && (
        <Review
          key={tab}
          lesson={lesson}
          layer={tab}
          dirty={dirty}
          busy={lesson.busy}
          onAction={(issueId, action) => issueAction(tab, issueId, action)}
          onRerun={() => run(tab === 'facts' ? 'qc_facts' : 'qc_teaching')}
        />
      )}
      {tab === 'preview' && <Preview lesson={lesson} dirty={dirty} />}
      {tab === 'history' && <History lesson={lesson} dirty={dirty} onRestore={(l) => setLesson(l)} />}
    </div>
  )
}
