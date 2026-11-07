import { useEffect, useState } from 'react'
import { api, errorText } from '../api'
import type { Lesson, Version } from '../types'
import { stamp } from '../util'
import { Markdown, sourceIndex } from './Markdown'

const WHO: Record<Version['author'], string> = { ai: 'AI', instructor: 'You', qc: 'QC fix' }

export function History({ lesson, dirty, onRestore }: { lesson: Lesson; dirty: boolean; onRestore: (l: Lesson) => void }) {
  const [versions, setVersions] = useState<Version[] | null>(null)
  const [selected, setSelected] = useState<Version | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.versions(lesson.id).then(setVersions, (e) => setError(errorText(e)))
  }, [lesson.id, lesson.version_count])

  const open = async (v: Version) => {
    try {
      setSelected(await api.version(lesson.id, v.id))
    } catch (e) {
      setError(errorText(e))
    }
  }

  const restore = async (v: Version) => {
    try {
      const updated = await api.restore(lesson.id, v.id)
      onRestore(updated)
      setSelected(null)
    } catch (e) {
      setError(errorText(e))
    }
  }

  if (error) return <div className="notice bad"><p>{error}</p></div>
  if (!versions) return <p className="muted">Loading…</p>
  if (!versions.length) return <p className="muted">No saved versions yet.</p>

  return (
    <>
      <p className="muted small" style={{ marginTop: -8 }}>
        Every AI draft, every save and every applied recommendation is kept. Restoring adds a new version, so nothing is
        overwritten.
      </p>
      <ul className="versions">
        {versions.map((v, i) => (
          <li key={v.id} className={selected?.id === v.id ? 'selected' : ''}>
            <span className="small muted">{stamp(v.created_at)}</span>
            <span>
              {v.note}
              <div className="who">
                {WHO[v.author]} · {(v.size / 1000).toFixed(1)}k characters{i === 0 ? ' · current' : ''}
              </div>
            </span>
            <span className="row">
              <button className="btn small quiet" onClick={() => open(v)}>
                View
              </button>
              {i > 0 && (
                <button className="btn small" disabled={dirty || lesson.busy} onClick={() => restore(v)}>
                  Restore
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>
      {selected?.content != null && (
        <>
          <div className="row" style={{ margin: '28px 0 12px' }}>
            <h2 className="section" style={{ margin: 0 }}>
              Version from {stamp(selected.created_at)}
            </h2>
            <span className="spacer" />
            <button className="btn quiet small" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          <article className="paper">
            <div className="prose">
              <Markdown text={selected.content} sources={sourceIndex(lesson.research)} />
            </div>
          </article>
        </>
      )}
    </>
  )
}
