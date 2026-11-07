import { useCallback, useEffect, useState } from 'react'
import { Link, Route, Routes, useParams } from 'react-router-dom'
import { api } from './api'
import { LessonPage } from './components/LessonPage'
import { NewLesson } from './components/NewLesson'
import type { LessonSummary, ServerStatus } from './types'
import { ago, lessonState } from './util'

function Sidebar({ lessons, status }: { lessons: LessonSummary[] | null; status: ServerStatus | null }) {
  const { id } = useParams()
  return (
    <aside className="sidebar">
      <Link to="/" className="wordmark">
        <b>Lectern</b>
        <span>lesson workbench</span>
      </Link>
      <Link to="/" className="btn block">
        New lesson
      </Link>
      <div>
        <div className="list-label">Lessons</div>
        {lessons === null && <div className="empty-list">Loading…</div>}
        {lessons?.length === 0 && <div className="empty-list">Nothing here yet. Your lessons will be listed here.</div>}
        <ul className="lesson-list">
          {lessons?.map((l) => {
            const s = lessonState(l)
            return (
              <li key={l.id}>
                <Link to={`/lessons/${l.id}`} className={`lesson-link ${l.id === id ? 'active' : ''}`}>
                  <span className="t">{l.title}</span>
                  <span className="m">
                    <span className={`dot ${s.tone}`} />
                    {s.label} · {ago(l.updated_at)}
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      </div>
      {status && (
        <div className="sidebar-foot">
          Writer: <code>{status.llm.model}</code>
          {status.llm.qc_model !== status.llm.model && (
            <>
              <br />
              Reviewers: <code>{status.llm.qc_model}</code>
            </>
          )}
          <br />
          Web: {status.research.web.split(' (')[0]}
        </div>
      )}
    </aside>
  )
}

export default function App() {
  const [lessons, setLessons] = useState<LessonSummary[] | null>(null)
  const [status, setStatus] = useState<ServerStatus | null>(null)

  const refresh = useCallback(() => {
    api.lessons().then(setLessons, () => setLessons((prev) => prev ?? []))
  }, [])

  useEffect(() => {
    refresh()
    api.status().then(setStatus, () => setStatus(null))
  }, [refresh])

  const layout = (page: React.ReactNode) => (
    <div className="shell">
      <Sidebar lessons={lessons} status={status} />
      <main className="main">{page}</main>
    </div>
  )

  return (
    <Routes>
      <Route path="/" element={layout(<NewLesson status={status} onCreated={refresh} />)} />
      <Route path="/lessons/:id/:tab?" element={layout(<LessonPage onChanged={refresh} />)} />
      <Route path="*" element={layout(<div className="page muted">Page not found.</div>)} />
    </Routes>
  )
}
