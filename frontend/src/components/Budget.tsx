import type { Timing } from '../types'

/** The 45-minute plan as a bar: one segment per section, width = minutes. */
export function Budget({ timing }: { timing: Timing }) {
  const counted = timing.sections.filter((s) => !s.optional && (s.planned ?? s.estimated) > 0.2)
  return (
    <div className="budget">
      <div className="budget-bar" role="img" aria-label="Time budget by section">
        {counted.map((s, i) => {
          const minutes = s.planned ?? s.estimated
          const over = s.planned != null && s.reading > s.planned * 1.25 + 1
          return (
            <div
              key={i}
              className={`budget-seg ${s.kind} ${over ? 'over' : ''}`}
              style={{ flexGrow: minutes, flexBasis: 0 }}
              title={`${s.heading}: planned ${s.planned ?? '?'} min, about ${s.reading} min of reading (${s.words} words)`}
            >
              {minutes >= 4 ? `${s.heading} · ${minutes}′` : ''}
            </div>
          )
        })}
      </div>
      <div className="budget-legend">
        <span>
          <b>{timing.planned_total}</b> of {timing.target} min planned · about{' '}
          <b>{Math.round(timing.estimated_total)}</b> min estimated
        </span>
        <span>
          <i className="swatch" style={{ background: 'var(--accent-soft)' }} />
          Reading
        </span>
        <span>
          <i className="swatch" style={{ background: '#dfe7f1' }} />
          Activity / check
        </span>
        <span className={timing.fits ? 'tag good' : 'tag warn'}>{timing.fits ? 'Fits 45 min' : 'Check timing'}</span>
      </div>
      {timing.warnings.length > 0 && (
        <ul className="bullets small" style={{ color: 'var(--warn)', marginTop: 8 }}>
          {timing.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
