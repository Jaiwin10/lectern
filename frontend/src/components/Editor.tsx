import { useEffect, useRef } from 'react'
import type { Lesson } from '../types'
import { ago } from '../util'
import { Budget } from './Budget'
import { Markdown, sourceIndex } from './Markdown'

interface Props {
  lesson: Lesson
  value: string
  dirty: boolean
  saving: boolean
  restored: boolean
  onChange: (text: string) => void
  onSave: () => void
  onDiscard: () => void
  onRegenerate: () => void
  busy: boolean
}

export function Editor({ lesson, value, dirty, saving, restored, onChange, onSave, onDiscard, onRegenerate, busy }: Props) {
  const saveRef = useRef(onSave)
  saveRef.current = onSave

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        saveRef.current()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const draftStep = lesson.steps.draft.status
  if (!lesson.content && !dirty) {
    if (draftStep === 'failed' || lesson.steps.research.status === 'failed') {
      return (
        <p className="muted">
          No lesson text yet. A step failed. Use <b>Retry this step</b> above.
        </p>
      )
    }
    return (
      <div className="working">
        {lesson.steps.research.status === 'running' ? 'Collecting sources…' : 'Writing the lesson from the sources…'}
        <div className="line" />
        <p className="small" style={{ marginTop: 18 }}>
          This usually takes one to two minutes. You can leave this page; the work continues.
        </p>
      </div>
    )
  }

  const sources = sourceIndex(lesson.research)
  return (
    <>
      {lesson.timing && <Budget timing={lesson.timing} />}
      {restored && (
        <div className="notice warn" style={{ marginBottom: 12 }}>
          <p>Restored unsaved edits from your last visit. Save them, or discard to go back to the saved version.</p>
        </div>
      )}
      <div className="editor-bar">
        <span className={`save-state ${dirty ? 'dirty' : ''}`}>
          <span className={`dot ${dirty ? '' : 'ok'}`} style={dirty ? { background: 'var(--warn)' } : undefined} />
          {saving ? 'Saving…' : dirty ? 'Unsaved changes' : `Saved ${ago(lesson.updated_at)}`}
        </span>
        <span className="spacer" />
        <button className="btn quiet" disabled={busy || dirty} onClick={onRegenerate} title="Write a new draft from the same research">
          Regenerate draft
        </button>
        {dirty && (
          <button className="btn" onClick={onDiscard}>
            Discard changes
          </button>
        )}
        <button className="btn primary" disabled={!dirty || saving} onClick={onSave}>
          Save <span className="kbd">⌘S</span>
        </button>
      </div>
      <div className="split">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          spellCheck
          aria-label="Lesson text in Markdown"
        />
        <div className="live">
          <div className="pane-label">Live preview</div>
          <div className="prose">
            <Markdown text={value} sources={sources} />
          </div>
        </div>
      </div>
    </>
  )
}
