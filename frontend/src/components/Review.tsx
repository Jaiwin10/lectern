import { useState } from 'react'
import type { Check, FactsReport, Issue, Layer, Lesson, TeachingReport } from '../types'
import { ago } from '../util'

type Action = 'apply' | 'apply-ai' | 'dismiss' | 'reopen'

interface Props {
  lesson: Lesson
  layer: Layer
  dirty: boolean
  busy: boolean
  onAction: (issueId: string, action: Action) => Promise<void>
  onRerun: () => void
}

const INTRO: Record<Layer, { title: string; text: string }> = {
  facts: {
    title: 'Research and factual accuracy',
    text: 'An independent reviewer checks each key claim against the collected sources, rates the sources, and looks for gaps or contradictions.',
  },
  teaching: {
    title: 'Instructional quality',
    text: 'A separate reviewer, who never sees the sources or the fact check, judges alignment with the objective, clarity, structure, examples, practice and timing.',
  },
}

const VERDICT: Record<string, { label: string; tone: string }> = {
  supported: { label: 'Supported', tone: 'good' },
  well_established: { label: 'Well established', tone: 'accent' },
  unsupported: { label: 'Unsupported', tone: 'warn' },
  misleading: { label: 'Misleading', tone: 'warn' },
  incorrect: { label: 'Incorrect', tone: 'bad' },
}

export function Review({ lesson, layer, dirty, busy, onAction, onRerun }: Props) {
  const step = lesson.steps[layer === 'facts' ? 'qc_facts' : 'qc_teaching']
  const report = layer === 'facts' ? lesson.qc_facts : lesson.qc_teaching
  const intro = INTRO[layer]

  const header = (
    <div className="row" style={{ marginBottom: 22, alignItems: 'flex-start' }}>
      <div style={{ flex: 1, minWidth: 260 }}>
        <p className="kicker">QC layer {layer === 'facts' ? 1 : 2}</p>
        <h2 className="section" style={{ margin: '0 0 6px', fontSize: 24 }}>
          {intro.title}
        </h2>
        <p className="muted small" style={{ margin: 0, maxWidth: '68ch' }}>
          {intro.text}
        </p>
      </div>
      {report && (
        <button className="btn" disabled={busy || dirty} onClick={onRerun} title={dirty ? 'Save your edits first' : ''}>
          Run review again
        </button>
      )}
    </div>
  )

  if (step.status === 'running' || step.status === 'pending') {
    return (
      <>
        {header}
        <div className="working">
          {step.status === 'running' ? 'Reviewing the lesson…' : 'Queued. Starts after the draft is ready.'}
          <div className="line" />
        </div>
      </>
    )
  }
  if (!report) {
    return (
      <>
        {header}
        {step.status === 'failed' ? (
          <div className="notice bad">
            <p>{step.error}</p>
            <button className="btn small" disabled={busy} onClick={onRerun}>
              Retry review
            </button>
          </div>
        ) : (
          <p className="muted">{step.error ?? 'This review has not run yet.'}</p>
        )}
      </>
    )
  }

  return (
    <>
      {header}
      {step.status === 'failed' && (
        <div className="notice bad" style={{ marginBottom: 16 }}>
          <p>The last run failed: {step.error} Showing the previous report.</p>
          <button className="btn small" disabled={busy} onClick={onRerun}>
            Retry
          </button>
        </div>
      )}
      {report.stale && (
        <div className="notice warn" style={{ marginBottom: 16 }}>
          <p>The lesson has changed since this review. Some findings may already be fixed or out of date.</p>
          <button className="btn small" disabled={busy || dirty} onClick={onRerun}>
            Review the current text
          </button>
        </div>
      )}

      <div className="review-head">
        {layer === 'facts' ? <FactsScore r={report as FactsReport} /> : <TeachingScore r={report as TeachingReport} />}
        <div>
          <p className="summary-text">{report.summary}</p>
          <p className="muted small" style={{ margin: 0 }}>
            Reviewed {ago(report.ran_at)} by {report.model}
          </p>
        </div>
      </div>

      <Issues issues={report.issues} dirty={dirty} busy={busy} onAction={onAction} />

      {layer === 'facts' ? <FactsDetail r={report as FactsReport} lesson={lesson} /> : <TeachingDetail r={report as TeachingReport} />}

      <h3 className="sub">Automated checks</h3>
      <Checks checks={report.checks} />
    </>
  )
}

// ---------------------------------------------------------------- scores

function FactsScore({ r }: { r: FactsReport }) {
  const counts = r.claims.reduce<Record<string, number>>((acc, c) => ({ ...acc, [c.verdict]: (acc[c.verdict] ?? 0) + 1 }), {})
  return (
    <div className="score">
      <div className="big">
        {r.score ?? '–'}
        <small>%</small>
      </div>
      <div className="cap">of {r.claims.length} key claims are supported by a source or well established</div>
      <div className="verdicts">
        {Object.entries(counts).map(([v, n]) => (
          <span key={v} className={`tag ${VERDICT[v]?.tone ?? ''}`}>
            {n} {VERDICT[v]?.label.toLowerCase() ?? v}
          </span>
        ))}
      </div>
    </div>
  )
}

function TeachingScore({ r }: { r: TeachingReport }) {
  const covered = r.coverage.filter((c) => c.coverage === 'full').length
  return (
    <div className="score">
      <div className="big">
        {r.score ?? '–'}
        <small> / 5</small>
      </div>
      <div className="cap">
        average rubric score · {covered} of {r.coverage.length} parts of the objective fully covered
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- issues

function Issues({ issues, dirty, busy, onAction }: { issues: Issue[]; dirty: boolean; busy: boolean; onAction: Props['onAction'] }) {
  const [filter, setFilter] = useState<'open' | 'applied' | 'dismissed'>('open')
  const shown = issues.filter((i) => i.status === filter)
  const count = (s: string) => issues.filter((i) => i.status === s).length
  return (
    <>
      <div className="row" style={{ margin: '28px 0 10px' }}>
        <h2 className="section" style={{ margin: 0 }}>
          Recommendations
        </h2>
        <span className="spacer" />
        <div className="filters">
          {(['open', 'applied', 'dismissed'] as const).map((f) => (
            <button key={f} className={`filter ${filter === f ? 'on' : ''}`} onClick={() => setFilter(f)}>
              {f[0].toUpperCase() + f.slice(1)} {count(f)}
            </button>
          ))}
        </div>
      </div>
      {dirty && filter === 'open' && (
        <div className="notice warn" style={{ marginBottom: 12 }}>
          <p>You have unsaved edits in the editor. Save them before applying recommendations.</p>
        </div>
      )}
      {shown.length === 0 && (
        <p className="muted small" style={{ padding: '8px 0 4px' }}>
          {filter === 'open' ? (issues.length ? 'Nothing left open.' : 'The reviewer found no issues.') : `No ${filter} recommendations.`}
        </p>
      )}
      {shown.map((issue) => (
        <IssueCard key={issue.id} issue={issue} disabled={busy || dirty} onAction={onAction} />
      ))}
    </>
  )
}

function IssueCard({ issue, disabled, onAction }: { issue: Issue; disabled: boolean; onAction: Props['onAction'] }) {
  const [working, setWorking] = useState<Action | null>(null)
  const act = async (a: Action) => {
    setWorking(a)
    try {
      await onAction(issue.id, a)
    } finally {
      setWorking(null)
    }
  }
  const hasFix = issue.fix.type !== 'none' && issue.fix.text
  return (
    <div className={`issue ${issue.status !== 'open' ? 'done' : ''}`}>
      <div className={`sev ${issue.severity}`} />
      <div className="body">
        <div className="top">
          <span className="id-chip">{issue.id}</span>
          <span className={`tag ${issue.severity === 'high' ? 'bad' : issue.severity === 'medium' ? 'warn' : ''}`}>
            {issue.severity}
          </span>
          <span>{issue.category}</span>
          {issue.location && <span>· {issue.location}</span>}
        </div>
        <p className="problem">{issue.problem}</p>
        <p className="suggestion">{issue.suggestion}</p>
        {(issue.excerpt || hasFix) && (
          <div className="diff">
            {issue.excerpt && <div className={`del ${issue.fix.type === 'insert_after' ? 'anchor' : ''}`}>{issue.excerpt}</div>}
            {hasFix && <div className="ins">{issue.fix.text}</div>}
          </div>
        )}
        <div className="actions">
          {issue.status === 'open' ? (
            <>
              {hasFix && (
                <button
                  className="btn primary small"
                  disabled={disabled || !issue.applicable || working !== null}
                  onClick={() => act('apply')}
                >
                  {working === 'apply' ? 'Applying…' : 'Apply change'}
                </button>
              )}
              <button className="btn small" disabled={disabled || working !== null} onClick={() => act('apply-ai')}>
                {working === 'apply-ai' ? 'Revising…' : 'Apply with AI'}
              </button>
              <button className="btn quiet small" disabled={working !== null} onClick={() => act('dismiss')}>
                Dismiss
              </button>
              {hasFix && !issue.applicable && (
                <span className="why-not">The quoted passage is no longer in the text. Use AI or edit by hand.</span>
              )}
            </>
          ) : (
            <>
              <span className="why-not">
                {issue.status === 'applied' ? 'Applied. The previous text is in History.' : 'Dismissed.'}
              </span>
              {issue.status === 'dismissed' && (
                <button className="btn quiet small" onClick={() => act('reopen')}>
                  Reopen
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- details

function FactsDetail({ r, lesson }: { r: FactsReport; lesson: Lesson }) {
  const titles: Record<string, string> = {}
  for (const s of [...(lesson.research?.web ?? []), ...(lesson.research?.books ?? [])]) titles[s.id] = s.title
  return (
    <>
      <h3 className="sub">Claims checked</h3>
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: '46%' }}>Claim</th>
            <th>Verdict</th>
            <th>Sources</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {r.claims.map((c, i) => (
            <tr key={i}>
              <td className="claim">{c.claim}</td>
              <td>
                <span className={`tag ${VERDICT[c.verdict]?.tone ?? ''}`}>{VERDICT[c.verdict]?.label ?? c.verdict}</span>
              </td>
              <td>
                {c.sources.map((s) => (
                  <span key={s} className="id-chip" title={titles[s]} style={{ marginRight: 6 }}>
                    {s}
                  </span>
                ))}
              </td>
              <td className="note">{c.note}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="two-col">
        <div>
          <h3 className="sub">Source reliability</h3>
          <table className="table">
            <tbody>
              {r.source_review.map((s) => (
                <tr key={s.source_id}>
                  <td style={{ width: 44 }}>
                    <span className="id-chip">{s.source_id}</span>
                  </td>
                  <td>
                    <div className="row" style={{ gap: 6 }}>
                      <span className="tag">relevance {s.relevance}</span>
                      <span className={`tag ${s.reliability === 'high' ? 'good' : s.reliability === 'low' ? 'bad' : ''}`}>
                        reliability {s.reliability}
                      </span>
                    </div>
                    <div className="note" style={{ marginTop: 4 }}>
                      {s.note}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h3 className="sub">Gaps and inconsistencies</h3>
          {r.gaps.length ? (
            <ul className="bullets small">
              {r.gaps.map((g, i) => (
                <li key={i}>{g}</li>
              ))}
            </ul>
          ) : (
            <p className="muted small">None found.</p>
          )}
        </div>
      </div>
    </>
  )
}

function TeachingDetail({ r }: { r: TeachingReport }) {
  return (
    <>
      <h3 className="sub">Objective coverage</h3>
      <table className="table">
        <thead>
          <tr>
            <th>Part of the objective</th>
            <th>Coverage</th>
            <th>Practised</th>
            <th>Where / note</th>
          </tr>
        </thead>
        <tbody>
          {r.coverage.map((c, i) => (
            <tr key={i}>
              <td className="claim">{c.component}</td>
              <td>
                <span className={`tag ${c.coverage === 'full' ? 'good' : c.coverage === 'missing' ? 'bad' : 'warn'}`}>
                  {c.coverage}
                </span>
              </td>
              <td>{c.practiced ? 'Yes' : <span style={{ color: 'var(--warn)' }}>No</span>}</td>
              <td className="note">
                {c.where && <b style={{ fontWeight: 500, color: 'var(--ink)' }}>{c.where}. </b>}
                {c.note}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="two-col">
        <div>
          <h3 className="sub">Rubric</h3>
          <div className="rubric">
            {r.rubric.map((x) => (
              <Row key={x.dimension} dimension={x.dimension} score={x.score} reason={x.reason} />
            ))}
          </div>
        </div>
        <div>
          <h3 className="sub">What works</h3>
          <ul className="bullets small">
            {r.strengths.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      </div>
    </>
  )
}

function Row({ dimension, score, reason }: { dimension: string; score: number; reason: string }) {
  return (
    <>
      <div style={{ fontWeight: 500 }}>{dimension}</div>
      <div>
        <span className="pips" aria-label={`${score} out of 5`}>
          {[1, 2, 3, 4, 5].map((n) => (
            <i key={n} className={n <= score ? 'on' : ''} />
          ))}
        </span>
      </div>
      <div className="reason note" style={{ color: 'var(--ink-2)', fontSize: 13 }}>
        {reason}
      </div>
    </>
  )
}

function Checks({ checks }: { checks: Check[] }) {
  const mark = { pass: '✓', warn: '!', fail: '×' }
  return (
    <ul className="checks">
      {checks.map((c) => (
        <li key={c.id} className={c.status}>
          <span className="mark">{mark[c.status]}</span>
          <span>
            {c.label}
            <div className="d">{c.detail}</div>
          </span>
        </li>
      ))}
    </ul>
  )
}
