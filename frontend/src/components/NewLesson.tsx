import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api, errorText } from '../api'
import type { ServerStatus } from '../types'

const SAMPLES = [
  {
    label: 'HTTP requests',
    title: 'HTTP Requests and Responses',
    objective: 'Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.',
  },
  {
    label: 'Git branching',
    title: 'Git Branching and Merging',
    objective: 'Create and switch between Git branches, merge a branch into main, and resolve a simple merge conflict.',
  },
]

export function NewLesson({ status, onCreated }: { status: ServerStatus | null; onCreated: () => void }) {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [objective, setObjective] = useState('')
  const [audience, setAudience] = useState('')
  const [fields, setFields] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const local: Record<string, string> = {}
    if (!title.trim()) local.title = 'Enter a lesson title.'
    if (!objective.trim()) local.objective = 'Enter a learning objective.'
    else if (objective.trim().split(/\s+/).length < 4) local.objective = 'Write the objective as a full sentence.'
    setFields(local)
    setError(null)
    if (Object.keys(local).length) return
    setSending(true)
    try {
      const lesson = await api.create(title, objective, audience)
      onCreated()
      navigate(`/lessons/${lesson.id}`)
    } catch (err) {
      if (err instanceof ApiError && err.fields) setFields(err.fields)
      setError(errorText(err))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="page narrow">
      <p className="kicker">New lesson</p>
      <h1 className="title">What are you teaching?</h1>
      <p className="objective" style={{ marginBottom: 28 }}>
        Give a title and one learning objective. Lectern researches the topic, writes a 45-minute lesson with cited
        sources, then has it checked twice: once for facts, once for teaching quality.
      </p>

      <div className="prefill">
        Try an example:
        {SAMPLES.map((s) => (
          <button
            key={s.label}
            type="button"
            className="linkish"
            onClick={() => {
              setTitle(s.title)
              setObjective(s.objective)
              setFields({})
            }}
          >
            {s.label}
          </button>
        ))}
      </div>

      <form onSubmit={submit} noValidate>
        <div className={`field ${fields.title ? 'invalid' : ''}`}>
          <label htmlFor="title">Lesson title</label>
          <input id="title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. HTTP Requests and Responses" maxLength={150} />
          {fields.title && <span className="error">{fields.title}</span>}
        </div>
        <div className={`field ${fields.objective ? 'invalid' : ''}`}>
          <label htmlFor="objective">Learning objective</label>
          <textarea
            id="objective"
            rows={3}
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            placeholder="What should learners be able to do after 45 minutes? Start with a verb: explain, compare, build…"
          />
          {fields.objective ? (
            <span className="error">{fields.objective}</span>
          ) : (
            <span className="hint">Both QC layers check the lesson against this sentence, so make it specific.</span>
          )}
        </div>
        <div className="field">
          <label htmlFor="audience">
            Audience <span className="muted">(optional)</span>
          </label>
          <input id="audience" value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="First-year engineering students who are new to the topic" />
        </div>
        {error && (
          <div className="notice bad" style={{ marginBottom: 16 }}>
            <p>{error}</p>
          </div>
        )}
        <div className="row">
          <button className="btn primary" type="submit" disabled={sending || status?.llm.configured === false} style={{ height: 40, padding: '0 20px' }}>
            {sending ? 'Starting…' : 'Research and write'}
          </button>
          <span className="muted small">Takes about two minutes. You can leave the page while it works.</span>
        </div>
        {status?.llm.configured === false && (
          <div className="notice bad" style={{ marginTop: 16 }}>
            <p>
              No API key is set for <b>{status.llm.provider}</b>. Add it to the <code>.env</code> file and restart the server.
            </p>
          </div>
        )}
      </form>

      <hr className="hr" />
      <h3 className="sub" style={{ marginTop: 0 }}>
        What happens next
      </h3>
      <ol className="how">
        <li>
          <b>Research</b>
          Searches the web{status ? ` (${status.research.web.split(' (')[0]})` : ''}, books and YouTube, and rates each source’s reliability.
        </li>
        <li>
          <b>Draft</b>
          Writes a lesson timed to 45 minutes, with examples, an activity and a knowledge check, citing every fact.
        </li>
        <li>
          <b>Fact check (QC 1)</b>
          Checks each key claim against the sources and flags unsupported or misleading ones.
        </li>
        <li>
          <b>Teaching review (QC 2)</b>
          A separate reviewer checks alignment with the objective, clarity, examples, practice and timing.
        </li>
      </ol>
    </div>
  )
}
