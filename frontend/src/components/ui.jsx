// Shared presentational pieces used by every tab.

export function Tile({ label, value, note, hero = false }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className={hero ? 'hero' : 'tile-value'}>{value}</div>
      {note && <div className="tile-note">{note}</div>}
    </div>
  )
}

export function Card({ title, sub, children, actions }) {
  return (
    <section className="card">
      {(title || actions) && (
        <div style={{ display: 'flex', alignItems: 'start', gap: 12 }}>
          <div style={{ flex: 1 }}>
            {title && <h3 className="card-title">{title}</h3>}
            {sub && <p className="card-sub">{sub}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  )
}

/**
 * Labelled magnitude rows. Identity is carried by the row label and the value,
 * so one hue is enough — no colour-only encoding anywhere.
 */
export function BarRows({ items, empty = 'Nothing yet.', formatValue }) {
  const max = Math.max(1, ...items.map((i) => i.value))
  if (!items.length) return <p className="muted small">{empty}</p>
  return (
    <div className="rows">
      {items.map((item) => (
        <div className="row-item" key={item.label}>
          <span className="row-label" title={item.label}>
            {item.label}
          </span>
          <span className="row-track">
            <span className="row-fill" style={{ width: `${(item.value / max) * 100}%` }} />
          </span>
          <span className="row-value">
            {formatValue ? formatValue(item) : item.value}
          </span>
        </div>
      ))}
    </div>
  )
}

export function Meter({ value, max = 100 }) {
  return (
    <div className="meter">
      <div className="meter-fill" style={{ width: `${Math.min(100, (value / max) * 100)}%` }} />
    </div>
  )
}

// Status word always appears inside the pill, so colour only reinforces it.
const PILL_TONE = {
  offer: 'green',
  rejected: 'red',
  interviewing: 'orange',
  applied: 'blue',
  solved: 'green',
  practiced: 'green',
  stuck: 'red',
  in_progress: 'orange',
  studying: 'orange',
  revisit: 'orange',
  cleared: 'green',
  pending: '',
  waiting: '',
  completed: 'green',
  current: 'orange',
  upcoming: '',
}

export function Pill({ children, tone }) {
  const cls = tone ?? PILL_TONE[String(children).toLowerCase()] ?? ''
  return <span className={`pill ${cls}`}>{label(children)}</span>
}

// A few stored values read better with a different word in the UI. The stored
// value never changes — only what the reader sees.
const DISPLAY_OVERRIDES = {
  saved: 'yet to apply',
}

export function label(value) {
  if (value === null || value === undefined || value === '') return '—'
  const key = String(value)
  return DISPLAY_OVERRIDES[key] ?? key.replace(/_/g, ' ')
}

export function Tags({ items }) {
  if (!items?.length) return <span className="muted small">—</span>
  return (
    <>
      {items.map((t) => (
        <span className="tag" key={t}>
          {t}
        </span>
      ))}
    </>
  )
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>
}

export function Field({ label: text, children }) {
  return (
    <div className="field">
      <label>{text}</label>
      {children}
    </div>
  )
}

export function ago(days) {
  if (days === null || days === undefined) return '—'
  if (days === 0) return 'today'
  if (days === 1) return '1 day'
  return `${days} days`
}

/** "3 days ago" / "today" — ago() already reads as a point in time at 0. */
export function since(days) {
  const text = ago(days)
  return text === 'today' || text === '—' ? text : `${text} ago`
}

export function plural(n, word) {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

export function pct(n) {
  return `${n ?? 0}%`
}
