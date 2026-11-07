import type { Lesson, StepName } from '../types'
import { STEP_ORDER } from '../util'

const NAMES: Record<StepName, string> = {
  research: 'Research',
  draft: 'Draft',
  qc_facts: 'Fact check',
  qc_teaching: 'Teaching review',
}

const RUNNING: Record<StepName, string> = {
  research: 'Searching web, books and YouTube…',
  draft: 'Writing the lesson…',
  qc_facts: 'Checking claims against sources…',
  qc_teaching: 'Reviewing against the objective…',
}

function doneText(lesson: Lesson, step: StepName): string {
  const r = lesson.research
  switch (step) {
    case 'research':
      return r ? `${r.web.length} pages · ${r.books.length} books · ${r.videos.length} videos` : 'Done'
    case 'draft':
      return lesson.timing ? `${lesson.timing.words.toLocaleString()} words · ~${Math.round(lesson.timing.estimated_total)} min` : 'Done'
    case 'qc_facts':
      return lesson.qc_facts?.score != null ? `${lesson.qc_facts.score}% of claims sound` : 'Done'
    case 'qc_teaching':
      return lesson.qc_teaching?.score != null ? `Rubric ${lesson.qc_teaching.score} / 5` : 'Done'
  }
}

export function Steps({ lesson, onRun, busy }: { lesson: Lesson; onRun: (s: StepName) => void; busy: boolean }) {
  return (
    <div className="steps">
      {STEP_ORDER.map((name, i) => {
        const step = lesson.steps[name]
        const tone =
          step.status === 'done' ? 'ok' : step.status === 'failed' ? 'bad' : step.status === 'running' ? 'busy' : ''
        let state = ''
        if (step.status === 'running') state = RUNNING[name]
        else if (step.status === 'pending') state = 'Queued'
        else if (step.status === 'done') state = doneText(lesson, name)
        else if (step.status === 'failed') state = 'Failed'
        else if (step.status === 'blocked') state = step.error ?? 'Waiting'
        else state = 'Not started'
        return (
          <div key={name} className={`step ${step.status === 'failed' ? 'failed' : ''}`}>
            <div className="n">0{i + 1}</div>
            <div className="name">
              <span className={`dot ${tone}`} />
              {NAMES[name]}
            </div>
            <div className="state">{state}</div>
            {step.status === 'failed' && (
              <>
                <div className="err">{step.error}</div>
                <button className="btn small" disabled={busy} onClick={() => onRun(name)}>
                  Retry this step
                </button>
              </>
            )}
          </div>
        )
      })}
    </div>
  )
}
