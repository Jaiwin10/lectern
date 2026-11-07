import type { Lesson } from '../types'
import { ago, duration } from '../util'

const TIER: Record<string, { label: string; tone: string }> = {
  high: { label: 'Official / standard', tone: 'good' },
  good: { label: 'Established reference', tone: 'accent' },
  fair: { label: 'Tutorial / community', tone: '' },
  unknown: { label: 'Unrated publisher', tone: 'warn' },
  low: { label: 'Blog / user content', tone: 'bad' },
}

export function Sources({ lesson, onRerun, busy }: { lesson: Lesson; onRerun: () => void; busy: boolean }) {
  const r = lesson.research
  if (!r) {
    return <p className="muted">{lesson.steps.research.status === 'running' ? 'Collecting sources…' : 'No research yet.'}</p>
  }
  const cited = new Set((lesson.content.match(/\[([SBV]\d+)\]/g) ?? []).map((m) => m.slice(1, -1)))

  return (
    <div className="page narrow" style={{ padding: 0, margin: 0, maxWidth: 860 }}>
      <div className="row" style={{ marginBottom: 6 }}>
        <p className="muted small" style={{ margin: 0 }}>
          Collected {ago(r.collected_at)} · Web: {r.providers.web || 'none'} · Books: {r.providers.books || 'none'} ·
          Videos: {r.providers.videos || 'none'}
        </p>
        <span className="spacer" />
        <button className="btn small" disabled={busy} onClick={onRerun}>
          Search again
        </button>
      </div>
      <p className="muted small" style={{ marginTop: 0 }}>
        Queries: {r.queries.map((q) => `“${q}”`).join(', ')}
      </p>
      {r.notes.length > 0 && (
        <div className="notice info" style={{ margin: '12px 0 4px' }}>
          <p>{r.notes.join(' ')}</p>
        </div>
      )}

      <h2 className="section">Web pages</h2>
      {r.web.map((s) => (
        <div className="source" key={s.id}>
          <span className="id-chip">{s.id}</span>
          <div>
            <div className="title">
              <a href={s.url} target="_blank" rel="noreferrer">
                {s.title}
              </a>
            </div>
            <div className="meta">
              <span>{s.domain}</span>
              <span className={`tag ${TIER[s.tier]?.tone ?? ''}`}>{TIER[s.tier]?.label ?? s.tier}</span>
              <span>via {s.provider}</span>
              {cited.has(s.id) ? <span className="tag accent">Cited in lesson</span> : <span>Not cited</span>}
            </div>
          </div>
          <details>
            <summary>Text the lesson was written from</summary>
            <div className="excerpt">{s.content}</div>
          </details>
        </div>
      ))}

      <h2 className="section">Books</h2>
      {r.books.length === 0 && <p className="muted small">No closely matching books were found.</p>}
      {r.books.map((b) => (
        <div className="source" key={b.id}>
          <span className="id-chip">{b.id}</span>
          <div>
            <div className="title">
              <a href={b.url} target="_blank" rel="noreferrer">
                {b.title}
              </a>
            </div>
            <div className="meta">
              <span>{b.authors.join(', ')}</span>
              {b.year && <span>{b.year}</span>}
              {b.publisher && <span>{b.publisher}</span>}
              <span>via {b.provider}</span>
              {cited.has(b.id) && <span className="tag accent">Cited in lesson</span>}
            </div>
          </div>
          {b.description && (
            <details>
              <summary>Publisher description</summary>
              <div className="excerpt">{b.description}</div>
            </details>
          )}
        </div>
      ))}

      <h2 className="section">YouTube</h2>
      <p className="muted small" style={{ marginTop: -4 }}>
        Each video was checked to exist and be embeddable through YouTube oEmbed before being offered to the writer.
      </p>
      {r.videos.length === 0 && <p className="muted small">No relevant videos could be verified.</p>}
      <div className="videos">
        {r.videos.map((v) => (
          <a className="video" key={v.id} href={v.url} target="_blank" rel="noreferrer">
            <div className="thumb">
              <img src={`https://i.ytimg.com/vi/${v.video_id}/mqdefault.jpg`} alt="" loading="lazy" />
              {v.duration_sec ? <span className="len">{duration(v.duration_sec)}</span> : null}
            </div>
            <span className="vt">{v.title}</span>
            <span className="vm">
              <span className="id-chip">{v.id}</span> · {v.channel}
              {cited.has(v.id) ? ' · in lesson' : ''}
            </span>
          </a>
        ))}
      </div>
    </div>
  )
}
