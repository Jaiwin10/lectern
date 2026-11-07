import { api } from '../api'
import type { Lesson } from '../types'
import { duration } from '../util'
import { Markdown, sourceIndex } from './Markdown'

export function Preview({ lesson, dirty }: { lesson: Lesson; dirty: boolean }) {
  if (!lesson.content) return <p className="muted">There is no lesson text to preview yet.</p>
  const r = lesson.research
  const cited = new Set((lesson.content.match(/\[([SBV]\d+)\]/g) ?? []).map((m) => m.slice(1, -1)))
  const citedWeb = r?.web.filter((s) => cited.has(s.id)) ?? []
  const consulted = r?.web.filter((s) => !cited.has(s.id)) ?? []
  const url = (kind: string) => api.exportUrl(lesson.id, kind)

  return (
    <>
      <div className="export-grid">
        <a className="btn primary" href={url('bundle')}>
          Download everything (.zip)
        </a>
        <a className="btn" href={url('lesson.md')}>
          Lesson .md
        </a>
        <a className="btn" href={url('lesson.html')} target="_blank" rel="noreferrer">
          Printable page / PDF
        </a>
        <a className="btn" href={url('references.md')}>
          References
        </a>
        <a className="btn" href={url('qc1.md')}>
          QC 1 report
        </a>
        <a className="btn" href={url('qc2.md')}>
          QC 2 report
        </a>
      </div>
      {dirty && (
        <div className="notice warn" style={{ marginBottom: 16 }}>
          <p>You have unsaved edits. The preview and exports show the last saved version.</p>
        </div>
      )}
      <p className="muted small" style={{ marginTop: -8 }}>
        The zip contains the lesson as Markdown and HTML, the references, both QC reports, and a JSON copy of everything. To
        get a PDF, open the printable page and use your browser’s Print → Save as PDF.
      </p>

      <article className="paper">
        <div className="prose">
          <Markdown text={lesson.content} sources={sourceIndex(r)} />

          {r && r.videos.length > 0 && !/^##\s+Watch/m.test(lesson.content) && (
            <>
              <h2>Videos</h2>
              <div className="videos" style={{ fontFamily: 'var(--sans)' }}>
                {r.videos.map((v) => (
                  <a key={v.id} className="video" href={v.url} target="_blank" rel="noreferrer">
                    <div className="thumb">
                      <img src={`https://i.ytimg.com/vi/${v.video_id}/mqdefault.jpg`} alt="" loading="lazy" />
                      {v.duration_sec ? <span className="len">{duration(v.duration_sec)}</span> : null}
                    </div>
                    <span className="vt">{v.title}</span>
                    <span className="vm">{v.channel}</span>
                  </a>
                ))}
              </div>
            </>
          )}

          {r && (
            <>
              <h2>References</h2>
              <ol className="refs" style={{ listStyle: 'none', paddingLeft: 0 }}>
                {citedWeb.map((s) => (
                  <li key={s.id} id={`ref-${s.id}`}>
                    <span className="id-chip">[{s.id}]</span> {s.title}. <i>{s.domain}</i>.{' '}
                    <a href={s.url} target="_blank" rel="noreferrer">
                      {s.url}
                    </a>
                  </li>
                ))}
                {r.books.map((b) => (
                  <li key={b.id}>
                    <span className="id-chip">[{b.id}]</span> {b.authors.join(', ')}
                    {b.year ? ` (${b.year})` : ''}. <i>{b.title}</i>
                    {b.publisher ? `. ${b.publisher}` : ''}.{' '}
                    <a href={b.url} target="_blank" rel="noreferrer">
                      Book details
                    </a>
                  </li>
                ))}
              </ol>
              {consulted.length > 0 && (
                <>
                  <p className="refs" style={{ fontWeight: 600, marginBottom: 6 }}>
                    Also consulted
                  </p>
                  <ul className="refs" style={{ paddingLeft: 18 }}>
                    {consulted.map((s) => (
                      <li key={s.id}>
                        {s.title}.{' '}
                        <a href={s.url} target="_blank" rel="noreferrer">
                          {s.domain}
                        </a>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </div>
      </article>
    </>
  )
}
